import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fixture_pack import nepal_event

from storm_shield.reticulum_mesh import LOOPBACK_BASE_PORT

# Real Node processes on fixed ports; run on demand, not on every PR (see docs/roadmap.md).
pytestmark = pytest.mark.mesh_integration

FIRST_HTTP_PORT = 8101
FIRST_TCP_PORT = 4350
# Its own loopback group, clear of the slots people run Nodes in by hand, so none of those dial in.
# scripts/stop-nodes.sh lists the ports this group listens on.
FIRST_LOOPBACK_SLOT = 60
NODE_COUNT = 3


class RunningNode:
    """A real Node process on one machine, joined to the others by loopback or fixed TCP addresses."""

    def __init__(self, slot: int, data_dir: Path, interface: str) -> None:
        self._slot = slot
        self._interface = interface
        self._data_dir = data_dir
        self.url = f"http://127.0.0.1:{FIRST_HTTP_PORT + slot}"
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        env = {
            **os.environ,
            "NODE_NAME": f"node-{self._slot}",
            "NODE_PORT": str(FIRST_HTTP_PORT + self._slot),
            "NODE_MESH_INTERFACE": self._interface,
            "NODE_LOOPBACK_SLOT": str(FIRST_LOOPBACK_SLOT + self._slot),
            "NODE_LOOPBACK_FIRST_SLOT": str(FIRST_LOOPBACK_SLOT),
            "NODE_TCP_PORT": str(FIRST_TCP_PORT + self._slot),
            "NODE_TCP_PEERS": ",".join(
                f"127.0.0.1:{FIRST_TCP_PORT + other}"
                for other in range(NODE_COUNT)
                if other != self._slot
            ),
            "NODE_DATA_DIR": str(self._data_dir),
        }
        self._process = subprocess.Popen(
            [sys.executable, "-c", "from storm_shield.main import run; run()"], env=env
        )

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=10)
            self._process = None

    def id(self) -> str:
        return str(self._get("/api/state")["id"])

    def heard_from(self) -> set[str]:
        return {entry["id"] for entry in self._get("/api/state")["nodes"]}

    def pressure_from(self, node: str) -> float:
        entry = next(entry for entry in self._get("/api/state")["nodes"] if entry["id"] == node)
        return float(entry["measurements"]["air_pressure"]["value"])

    def age_of_reading_from(self, node: str) -> float:
        entry = next(entry for entry in self._get("/api/state")["nodes"] if entry["id"] == node)
        return float(entry["age_s"])

    def _get(self, path: str) -> Any:
        return httpx.get(f"{self.url}{path}").json()


def _eventually(check: Callable[[], bool], seconds: float = 40) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if check():
                return
        except (httpx.HTTPError, StopIteration):
            pass
        if time.monotonic() > deadline:
            raise AssertionError("the Nodes did not reach the expected state in time")
        time.sleep(0.5)


def _fail_if_ports_are_taken() -> None:
    """A Node left running elsewhere would answer in place of ours; say so instead of timing out."""
    ports = [
        base + slot
        for base in (FIRST_HTTP_PORT, FIRST_TCP_PORT, LOOPBACK_BASE_PORT + FIRST_LOOPBACK_SLOT)
        for slot in range(NODE_COUNT)
    ]
    taken = []
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                taken.append(port)
    if taken:
        pytest.fail(
            f"ports {taken} already have a listener, probably a Node left running; "
            "run scripts/stop-nodes.sh and try again"
        )


def _each_hears_exactly(nodes: list[RunningNode], ids: set[str]) -> bool:
    """Fails at once on a stranger: waiting would only end in a timeout that hides who dialed in."""
    heard = [node.heard_from() for node in nodes]
    strangers = set().union(*heard) - ids
    if strangers:
        raise AssertionError(
            f"the Nodes heard {sorted(strangers)} from outside this test, "
            "probably a Node left running that dials these ports; run scripts/stop-nodes.sh"
        )
    return all(entry == ids for entry in heard)


@pytest.fixture(params=["loopback", "tcp"])
def nodes(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[list[RunningNode]]:
    _fail_if_ports_are_taken()
    running = [
        RunningNode(slot, tmp_path / f"node-{slot}", request.param) for slot in range(NODE_COUNT)
    ]
    for node in running:
        node.start()
    yield running
    for node in running:
        node.stop()


def test_nodes_find_each_other_and_a_reading_crosses_the_mesh(nodes: list[RunningNode]) -> None:
    _eventually(lambda: all(len(node.id()) == 12 for node in nodes))
    ids = {node.id() for node in nodes}
    assert len(ids) == 3
    _eventually(lambda: _each_hears_exactly(nodes, ids))

    porch_id = nodes[0].id()
    first_moment = nepal_event().weather[0].pressure_hpa
    _eventually(lambda: nodes[2].pressure_from(porch_id) == first_moment)


def test_a_restarted_node_keeps_its_id_and_the_others_survive_its_absence(
    nodes: list[RunningNode],
) -> None:
    _eventually(lambda: all(len(node.id()) == 12 for node in nodes))
    first_id = nodes[0].id()
    nodes[0].stop()
    second_id = nodes[1].id()
    # Younger than the 3 s between readings, so it arrived after the first Node stopped.
    _eventually(lambda: nodes[2].age_of_reading_from(second_id) < 3)

    nodes[0].start()
    _eventually(lambda: nodes[0].id() == first_id)
