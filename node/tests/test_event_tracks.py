import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from meshed_nodes import MeshedNodes

from storm_shield.community_reading import Position, Reading
from storm_shield.region import RegionError, events_dir, load_region, region_path
from storm_shield.replay import Event, SensorSpot, load_events, read_event_file

pytestmark = pytest.mark.usefixtures("nepal_region")

NEW_KINDS = {"air_temperature": "°C", "humidity": "%", "wind_speed": "m/s"}
MADE_UP = {"nepal": "made-up-flash-flood", "fort-myers": "made-up-storm-surge"}
REAL = {"nepal": "bhote-koshi-2026", "fort-myers": "ian-2022"}


def _event(region: str, event_id: str) -> Event:
    return load_events(load_region(region_path(region)))[event_id]


def _track(kind: str = "wind_speed", **fields: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "unit": "m/s",
        "decimals": 1,
        "points": [[0, 2.0], [3600, 8.0]],
        **fields,
    }


def _write_event_with(tmp_path: Path, tracks: list[dict[str, Any]]) -> Path:
    event = json.loads((events_dir("nepal") / "made-up-flash-flood.json").read_text())
    path = tmp_path / "made-up-flash-flood.json"
    path.write_text(json.dumps({**event, "tracks": tracks}))
    return path


def _readings(event: Event, elapsed: int) -> dict[str, Reading]:
    """What a Sensor beside the Event's first station reads `elapsed` seconds in."""
    spot = SensorSpot(Position(27.9, 85.9), river_km=3.4, ground_m=1.0)
    readings = event.readings_at(spot, event.start_unix + elapsed, datetime.now(UTC))
    return {reading.kind: reading for reading in readings}


@pytest.mark.parametrize("region", ["nepal", "fort-myers"])
def test_a_made_up_event_reads_the_three_new_kinds_in_their_wire_units(region: str) -> None:
    event = _event(region, MADE_UP[region])
    readings = _readings(event, 600)

    assert {
        kind: reading.unit for kind, reading in readings.items() if kind in NEW_KINDS
    } == NEW_KINDS


@pytest.mark.parametrize("region", ["nepal", "fort-myers"])
def test_a_real_event_has_no_tracks_and_reads_no_new_kinds(region: str) -> None:
    event = _event(region, REAL[region])
    readings = _readings(event, 600)

    assert event.tracks == []
    assert not set(readings) & set(NEW_KINDS)


@pytest.mark.parametrize("region", ["nepal", "fort-myers"])
def test_the_flood_four_read_the_same_with_and_without_the_tracks(region: str) -> None:
    event = _event(region, MADE_UP[region])
    without = event.model_copy(update={"tracks": []})

    flood_four = {"water_level", "rain_rate", "soil_moisture", "air_pressure"}
    for elapsed in (0, 1234, 3000):
        kept = {k: r.value for k, r in _readings(event, elapsed).items() if k in flood_four}
        assert kept == {k: r.value for k, r in _readings(without, elapsed).items()}


def test_a_track_runs_on_straight_lines_between_its_points(tmp_path: Path) -> None:
    event = read_event_file(_write_event_with(tmp_path, [_track()]))

    winds = [_readings(event, elapsed)["wind_speed"].value for elapsed in (0, 1800, 3600, 9999)]

    assert winds == [2.0, 5.0, 8.0, 8.0]


def test_a_track_rounds_to_its_decimals(tmp_path: Path) -> None:
    event = read_event_file(_write_event_with(tmp_path, [_track(decimals=0)]))

    assert _readings(event, 1000)["wind_speed"].value == 4


@pytest.mark.parametrize(
    ("tracks", "complaint"),
    [
        ([_track("rain_rate")], "rain_rate"),
        ([_track("water_level")], "water_level"),
        ([_track("camera", unit="pic")], "camera"),
        ([_track(), _track()], "wind_speed"),
        ([_track(points=[[0, 1.0], [0, 2.0]])], "wind_speed"),
        ([_track(points=[[10, 1.0], [5, 2.0]])], "wind_speed"),
        ([_track(points=[])], "wind_speed"),
        ([_track(points=[[0, math.nan]])], "wind_speed"),
        ([_track(points=[[0, math.inf]])], "wind_speed"),
        ([_track(decimals=-1)], "wind_speed"),
    ],
)
def test_a_bad_track_stops_the_event_loading_and_names_the_event_and_track(
    tmp_path: Path, tracks: list[dict[str, Any]], complaint: str
) -> None:
    path = _write_event_with(tmp_path, tracks)

    with pytest.raises(RegionError) as refused:
        read_event_file(path)

    assert "made-up-flash-flood" in str(refused.value)
    assert complaint in str(refused.value)


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _kinds_heard(meshed_nodes: MeshedNodes, node: str) -> dict[str, Any]:
    nodes = meshed_nodes["hub"].get("/api/state").json()["nodes"]
    return next((n["measurements"] for n in nodes if n["id"] == node), {})


def test_a_sensor_sends_the_tracks_its_measures_name_and_the_hub_holds_them(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor(
        "mast", measures="rain_rate,air_temperature,humidity,wind_speed", river_km=3.4
    )
    meshed_nodes.start_sensor("plain")
    assert (
        meshed_nodes["hub"].post("/api/replay/start", json={"event": MADE_UP["nepal"]}).status_code
        == 200
    )

    _wait_until(lambda: "wind_speed" in _kinds_heard(meshed_nodes, "mast"))
    _wait_until(lambda: "rain_rate" in _kinds_heard(meshed_nodes, "plain"))

    mast = _kinds_heard(meshed_nodes, "mast")
    assert {kind: mast[kind]["unit"] for kind in NEW_KINDS} == NEW_KINDS
    assert not set(NEW_KINDS) & set(_kinds_heard(meshed_nodes, "plain"))
