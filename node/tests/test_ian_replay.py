"""The Hurricane Ian Replay on Fort Myers: its NWS Official Alerts at their Event clock times, and the
Fort Myers gauge's record playing as a REPLAY Official Gauge."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fort_myers_pack import build_fort_myers_pack
from meshed_nodes import MeshedNodes

from storm_shield import region
from storm_shield.region import REGIONS_DIR

EVENT_START = 1664359200
RATE = 30
# Real seconds after the start until the Event clock reads 12:36 Eastern, and 18:30.
TO_NOON_ALERT = (6 * 3600 + 36 * 60) / RATE
TO_SURGE_PEAK = 12.5 * 3600 / RATE
NOON_ALERT = {
    "id": "test-flash-flood-warning",
    "date": "2022-09-28",
    "at": "12:36:00",
    "issuer": "nws_tbw",
    "headline": "Flash Flood Warning",
    "applies_to": [],
    "source": "nws-tbw-warnings",
}


@pytest.fixture
def ian_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, bytes]:
    """Fort Myers with Ian as its only Event, and one more alert in the window to see it arrive."""
    folder = tmp_path / "regions" / "fort-myers"
    (folder / "events").mkdir(parents=True)
    (folder / "region.json").write_bytes((REGIONS_DIR / "fort-myers" / "region.json").read_bytes())
    ian: dict[str, Any] = json.loads((REGIONS_DIR / "fort-myers/events/ian-2022.json").read_text())
    ian["official_alerts"].append(NOON_ALERT)
    (folder / "events" / "ian-2022.json").write_text(json.dumps(ian))
    monkeypatch.setattr(region, "REGIONS_DIR", tmp_path / "regions")
    return tmp_path / "packs", build_fort_myers_pack()


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _state(meshed_nodes: MeshedNodes) -> dict[str, Any]:
    state: dict[str, Any] = meshed_nodes["hub"].get("/api/state").json()
    return state


def _headlines(meshed_nodes: MeshedNodes) -> list[str]:
    return [alert["headline"] for alert in _state(meshed_nodes)["official_alerts"]]


def _start_ian(meshed_nodes: MeshedNodes, pack: tuple[Path, bytes]) -> None:
    meshed_nodes.start_hub(pack, region="fort-myers")
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200


def test_the_alerts_already_in_force_show_at_the_start_with_their_own_times(
    meshed_nodes: MeshedNodes, ian_pack: tuple[Path, bytes]
) -> None:
    _start_ian(meshed_nodes, ian_pack)

    _wait_until(lambda: len(_state(meshed_nodes)["official_alerts"]) == 3)
    alerts = _state(meshed_nodes)["official_alerts"]
    assert [(alert["headline"], alert["issued"]) for alert in alerts] == [
        ("Flood Watch", "2022-09-26T17:00:00-04:00"),
        ("Storm Surge Warning", "2022-09-26T17:10:00-04:00"),
        ("Hurricane Warning", "2022-09-27T05:08:00-04:00"),
    ]
    assert {(alert["mode"], alert["source"]) for alert in alerts} == {("replay", "nws_tbw")}


def test_an_alert_in_the_window_shows_at_its_event_clock_time_and_not_before(
    meshed_nodes: MeshedNodes, ian_pack: tuple[Path, bytes]
) -> None:
    _start_ian(meshed_nodes, ian_pack)
    meshed_nodes.advance(TO_NOON_ALERT - 1)
    _wait_until(lambda: len(_headlines(meshed_nodes)) == 3)
    time.sleep(0.1)
    assert "Flash Flood Warning" not in _headlines(meshed_nodes)

    meshed_nodes.advance(1)
    _wait_until(lambda: "Flash Flood Warning" in _headlines(meshed_nodes))


def test_the_fort_myers_gauge_record_plays_as_a_replay_official_gauge(
    meshed_nodes: MeshedNodes, ian_pack: tuple[Path, bytes]
) -> None:
    _start_ian(meshed_nodes, ian_pack)
    meshed_nodes.advance(TO_SURGE_PEAK)

    def gauge() -> dict[str, Any]:
        gauges: list[dict[str, Any]] = _state(meshed_nodes)["official_gauges"]
        return gauges[0]

    # 7.257 ft above MHHW at 18:30, and the gauge's datum offset to the Region's NAVD88.
    _wait_until(lambda: gauge()["level_m"] == pytest.approx(2.297, abs=0.001))
    assert gauge()["mode"] == "replay"
    assert gauge()["observed"] == EVENT_START + 12.5 * 3600


def test_the_event_list_names_no_reconstructed_stations_for_ian(
    meshed_nodes: MeshedNodes, ian_pack: tuple[Path, bytes]
) -> None:
    meshed_nodes.start_hub(ian_pack, region="fort-myers")

    [ian] = meshed_nodes["hub"].get("/api/replay/events").json()["events"]
    assert ian["reconstructed_stations"] == []
