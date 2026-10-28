import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import RNS
from fort_myers_pack import REGION_FILE, build_fort_myers_pack
from meshed_nodes import MeshedNodes
from terrarium import terrarium_png

from storm_shield import region
from storm_shield.community_reading import Position
from storm_shield.community_warning import CommunityWarning
from storm_shield.replay import Event, SensorSpot
from storm_shield.reticulum_mesh import SIGNATURE_LENGTH
from storm_shield.terrain import tile_position

# 06:00 EDT on 28 Sep 2022, the first moment of the fixture Event.
EVENT_START = 1664359200
RATE = 30
# The bay shore, where the fixture's one station stands, on ground at the datum.
SHORE = (26.4507, -81.9533)
# A metre up: dry until the water passes 1 m, about an hour into the Event.
LOW = (26.45, -81.88)
# Inland on 10 m of ground, which the Event's water never reaches.
INLAND = (26.45, -81.80)
STATION: dict[str, Any] = {
    "id": "shore",
    "label": "Bay shore",
    "pos": list(SHORE),
    # 0.4 m at the start, rising 2 m over three hours.
    "series": [[0, 0.4], [10800, 2.4]],
}
COAST_EVENT: dict[str, Any] = {
    "id": "coast-fixture",
    "label": "A made-up storm surge",
    "hazard": "storm_surge",
    "real": False,
    "date": "2022-09-28",
    "utc_offset": "-04:00",
    "start": "06:00:00",
    "end": "09:00:00",
    "start_unix": EVENT_START,
    "rate": RATE,
    "sources": {},
    "phases": [],
    "internet_cue": {"at": "08:00:00"},
    "official_alerts": [],
    "surface": {"datum": "NAVD88", "unit": "m", "stations": [STATION]},
    "weather": [{"t": 0, "rain_mmh": 12.0, "soil_pct": 40.0, "pressure_hpa": 990.0}],
}


def _tile_path(spot: tuple[float, float]) -> str:
    x, y = tile_position(*spot, 12)
    return f"elevation/12/{int(x)}/{int(y)}.png"


@pytest.fixture
def coast_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, bytes]:
    """Fort Myers with the fixture Event as its only one, and a pack whose terrain puts the shore at
    0 m, the low spot at 1 m and the inland spot at 10 m."""
    folder = tmp_path / "regions" / "fort-myers"
    (folder / "events").mkdir(parents=True)
    (folder / "region.json").write_bytes(REGION_FILE.read_bytes())
    (folder / "events" / "coast-fixture.json").write_text(json.dumps(COAST_EVENT))
    monkeypatch.setattr(region, "REGIONS_DIR", tmp_path / "regions")
    terrain = {
        _tile_path(SHORE): terrarium_png(0),
        _tile_path(LOW): terrarium_png(1),
        _tile_path(INLAND): terrarium_png(10),
    }
    return tmp_path / "packs", build_fort_myers_pack(terrain)


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _measurements(meshed_nodes: MeshedNodes, node: str) -> dict[str, Any]:
    nodes = meshed_nodes["hub"].get("/api/state").json()["nodes"]
    entry = next((entry for entry in nodes if entry["id"] == node), None)
    return {} if entry is None else dict(entry["measurements"])


def _start_sensors(
    meshed_nodes: MeshedNodes, pack: tuple[Path, bytes], **spots: tuple[float, float]
) -> None:
    meshed_nodes.start_hub(pack, region="fort-myers")
    for name, (latitude, longitude) in spots.items():
        meshed_nodes.start_sensor(name, cache_pack=pack, latitude=latitude, longitude=longitude)


def test_a_shore_sensor_reports_the_water_and_one_on_high_ground_reports_none(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    _start_sensors(meshed_nodes, coast_pack, shore=SHORE, inland=INLAND)
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    # A minute later the Event clock is half an hour in: the shore's water stands at 0.733 m.
    meshed_nodes.advance(60)
    _wait_until(
        lambda: _measurements(meshed_nodes, "shore").get("water_level", {}).get("value") == 0.733
    )
    _wait_until(lambda: "air_pressure" in _measurements(meshed_nodes, "inland"))
    assert "water_level" not in _measurements(meshed_nodes, "inland")


def _water_level(meshed_nodes: MeshedNodes, node: str) -> float | None:
    value: float | None = _measurements(meshed_nodes, node).get("water_level", {}).get("value")
    return value


def _warning_log(meshed_nodes: MeshedNodes) -> list[dict[str, Any]]:
    return meshed_nodes["hub"].get("/api/warnings").json()["warnings"]  # type: ignore[no-any-return]


def _start_shore_sensor_and_play(meshed_nodes: MeshedNodes, pack: tuple[Path, bytes]) -> None:
    _start_sensors(meshed_nodes, pack, shore=SHORE)
    assert meshed_nodes["shore"].post("/api/registry/signup").status_code == 200
    _wait_until(
        lambda: (
            meshed_nodes["hub"].post("/api/registry/accept", json={"id": "shore"}).status_code
            == 200
        )
    )
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200


def _set_warning_height(tmp_path: Path, feet: float) -> None:
    region_file = tmp_path / "regions" / "fort-myers" / "region.json"
    raw = json.loads(region_file.read_text())
    raw["rules"]["flood_warning"]["storm_surge"]["warning_height"] = {"value": feet, "unit": "ft"}
    region_file.write_text(json.dumps(raw))


def test_a_registered_shore_sensor_passing_the_warning_height_while_rising_fires_one_warning(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    _start_shore_sensor_and_play(meshed_nodes, coast_pack)
    # Half an hour into the Event the shore's 0.733 m is still below the Region's 3 ft.
    meshed_nodes.advance(60)
    _wait_until(lambda: _water_level(meshed_nodes, "shore") == 0.733)
    assert _warning_log(meshed_nodes) == []

    # An hour in, 1.067 m and rising 2 m in three hours.
    meshed_nodes.advance(60)
    _wait_until(lambda: len(_warning_log(meshed_nodes)) == 1)
    warning = _warning_log(meshed_nodes)[0]
    assert warning["hazard"] == "storm_surge"
    assert warning["origin"] == "shore"
    assert warning["origin_km"] is None
    assert warning["level_m"] == 1.067
    assert warning["rise_m_per_h"] == pytest.approx(0.667, abs=0.001)
    assert warning["surge_t"] == EVENT_START + 3600

    # Still above and still rising: the same warning holds.
    meshed_nodes.advance(30)
    _wait_until(lambda: _water_level(meshed_nodes, "shore") == 1.233)
    assert len(_warning_log(meshed_nodes)) == 1


def test_a_higher_warning_height_fires_later(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes], tmp_path: Path
) -> None:
    _set_warning_height(tmp_path, 5)
    _start_shore_sensor_and_play(meshed_nodes, coast_pack)
    meshed_nodes.advance(120)
    _wait_until(lambda: _water_level(meshed_nodes, "shore") == 1.067)
    assert _warning_log(meshed_nodes) == []

    # Two hours in, 1.733 m: past 5 ft (1.524 m).
    meshed_nodes.advance(120)
    _wait_until(lambda: len(_warning_log(meshed_nodes)) == 1)
    assert _warning_log(meshed_nodes)[0]["level_m"] == 1.733


def test_an_unverified_shore_sensor_never_fires_the_storm_surge_warning(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    _start_sensors(meshed_nodes, coast_pack, shore=SHORE)
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    meshed_nodes.advance(120)
    _wait_until(lambda: _water_level(meshed_nodes, "shore") == 1.067)

    assert _warning_log(meshed_nodes) == []


def test_water_standing_above_the_warning_height_fires_nothing_until_it_rises(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    meshed_nodes.start_hub(coast_pack, region="fort-myers")
    meshed_nodes.announce_sign_up("pier", "pier")
    assert meshed_nodes["hub"].post("/api/registry/accept", json={"id": "pier"}).status_code == 200
    # A high tide that has turned: 1.2 m, above the Region's 3 ft, and not rising.
    meshed_nodes.hear_from("pier", water_cm=120)
    meshed_nodes.advance(60)
    meshed_nodes.hear_from("pier", water_cm=120)
    assert _warning_log(meshed_nodes) == []

    meshed_nodes.advance(60)
    meshed_nodes.hear_from("pier", water_cm=140)
    assert [w["origin"] for w in _warning_log(meshed_nodes)] == ["pier"]


def test_the_storm_surge_warning_fits_one_reticulum_packet(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    _start_shore_sensor_and_play(meshed_nodes, coast_pack)
    meshed_nodes.advance(120)
    _wait_until(lambda: len(_warning_log(meshed_nodes)) == 1)
    # As a real Node's 12-character id would make it, with every number at full length.
    longest = CommunityWarning.model_validate(_warning_log(meshed_nodes)[0]).model_copy(
        update={
            "nodes": ["b7e1f40a92c5"],
            "origin": "b7e1f40a92c5",
            "level_m": -1234.567,
            "rise_m_per_h": -1234.567,
        }
    )
    assert SIGNATURE_LENGTH + len(longest.model_dump_json().encode()) <= RNS.Packet.PLAIN_MDU


def test_a_spot_turns_wet_once_the_water_passes_its_ground(
    meshed_nodes: MeshedNodes, coast_pack: tuple[Path, bytes]
) -> None:
    _start_sensors(meshed_nodes, coast_pack, low=LOW)
    _wait_until(lambda: "air_pressure" in _measurements(meshed_nodes, "low"))
    assert "water_level" not in _measurements(meshed_nodes, "low")
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    # Two minutes on, an hour into the Event: the water is at 1.067 m, above the low spot's 1 m.
    meshed_nodes.advance(120)
    _wait_until(
        lambda: _measurements(meshed_nodes, "low").get("water_level", {}).get("value") == 1.067
    )


@pytest.mark.usefixtures("coast_pack")
def test_a_damaged_terrain_tile_reads_as_dry_and_the_sensor_keeps_publishing(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    # The fixture's Region folder, with a pack whose shore tile is not a PNG.
    pack = (tmp_path / "damaged", build_fort_myers_pack({_tile_path(SHORE): b"not a png"}))
    _start_sensors(meshed_nodes, pack, shore=SHORE)
    _wait_until(lambda: "air_pressure" in _measurements(meshed_nodes, "shore"))
    assert "water_level" not in _measurements(meshed_nodes, "shore")


def test_the_level_between_stations_is_blended_by_distance() -> None:
    far_station = STATION | {"id": "far", "pos": [SHORE[0], INLAND[1]], "series": [[0, 2.4]]}
    event = Event.model_validate(
        COAST_EVENT
        | {"surface": {"datum": "NAVD88", "unit": "m", "stations": [STATION, far_station]}}
    )
    midway = Position(SHORE[0], (SHORE[1] + INLAND[1]) / 2)
    readings = event.readings_at(SensorSpot(midway, None, 0.0), EVENT_START, datetime.now(UTC))
    water = next(reading for reading in readings if reading.kind == "water_level")
    # Equally far from both, so the plain average of 0.4 m and 2.4 m.
    assert water.value == 1.4


def test_a_storm_surge_event_needs_a_coast_surface() -> None:
    river_surface = {
        "unit": "m",
        "stations": [{"id": "s", "label": "S", "river_km": 1.0, "series": [[0, 1.0]]}],
    }
    with pytest.raises(ValueError, match="storm_surge Event needs a coast surface"):
        Event.model_validate(COAST_EVENT | {"surface": river_surface})
