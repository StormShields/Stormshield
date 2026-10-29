import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

pytestmark = pytest.mark.usefixtures("nepal_region")

# Where the Event file puts the Syabrubesi gauge; its level at the first moment is 1.5 m.
S2_KM = 14.6


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _entries_by_node(client: TestClient) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in client.get("/api/state").json()["nodes"]}


def _values_by_node_and_kind(client: TestClient) -> dict[tuple[str, str], float]:
    return {
        (entry["id"], kind): measurement["value"]
        for entry in client.get("/api/state").json()["nodes"]
        for kind, measurement in entry["measurements"].items()
    }


def test_each_node_lists_its_own_readings_and_the_others(meshed_nodes: MeshedNodes) -> None:
    for name in ["porch", "garage", "creek"]:
        meshed_nodes.start_sensor(name)
    _wait_until(
        lambda: set(_entries_by_node(meshed_nodes["porch"])) == {"porch", "garage", "creek"}
    )


def test_a_reading_on_one_node_shows_up_on_another(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_sensor("garage")
    meshed_nodes.start_sensor("porch", river_km=S2_KM)
    _wait_until(
        lambda: (
            _values_by_node_and_kind(meshed_nodes["garage"]).get(("porch", "water_level")) == 1.5
        )
    )


def test_readings_from_other_nodes_are_aged_and_labeled_simulated(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_sensor("porch")
    meshed_nodes.start_sensor("garage")
    _wait_until(lambda: "porch" in _entries_by_node(meshed_nodes["garage"]))
    from_porch = _entries_by_node(meshed_nodes["garage"])["porch"]
    assert from_porch["simulated"]
    assert from_porch["age_s"] >= 0


def test_removing_a_node_leaves_the_others_working(meshed_nodes: MeshedNodes) -> None:
    for name in ["porch", "garage", "creek"]:
        meshed_nodes.start_sensor(name)
    meshed_nodes.remove("garage")
    # The rain at the Event's first moment is 3 mm/h.
    _wait_until(
        lambda: _values_by_node_and_kind(meshed_nodes["porch"]).get(("creek", "rain_rate")) == 3
    )
    _wait_until(
        lambda: _values_by_node_and_kind(meshed_nodes["creek"]).get(("porch", "rain_rate")) == 3
    )


def test_positions_shared_between_nodes_are_fuzzed_to_about_200_metres(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_sensor("porch")
    meshed_nodes.start_sensor("garage")
    _wait_until(lambda: "porch" in _entries_by_node(meshed_nodes["garage"]))
    from_porch = _entries_by_node(meshed_nodes["garage"])["porch"]
    assert tuple(from_porch["position"]) == (27.974, 85.186)


def test_a_restarted_node_is_heard_again_though_its_seq_starts_over(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_sensor("porch")
    meshed_nodes.start_sensor("garage")
    _wait_until(lambda: "porch" in _entries_by_node(meshed_nodes["garage"]))
    meshed_nodes.remove("porch")
    meshed_nodes.advance(16)
    assert _entries_by_node(meshed_nodes["garage"])["porch"]["age_s"] >= 16
    meshed_nodes.start_sensor("porch")
    _wait_until(lambda: _entries_by_node(meshed_nodes["garage"])["porch"]["age_s"] < 5)
