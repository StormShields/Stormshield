import logging
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fixture_pack import nepal_event
from meshed_nodes import MeshedNodes

from storm_shield.community_reading import Measurement
from storm_shield.region import load_region, region_path

pytestmark = pytest.mark.usefixtures("nepal_region")

# A storm in three steps, as (pressure hPa, rain mm/h, water cm, soil %). The last is High from
# heavy rain on rising water and stays under the Surge size.
STORM_STEPS = [(990, 0, 100, 32), (985, 12, 350, 55), (980, 30, 390, 85)]


def _hear_step(meshed_nodes: MeshedNodes, sender: str, step: int) -> None:
    pressure_hpa, rain_mmh, water_cm, soil_pct = STORM_STEPS[step - 1]
    meshed_nodes.hear_from(
        sender, pressure_hpa=pressure_hpa, rain_mmh=rain_mmh, water_cm=water_cm, soil_pct=soil_pct
    )


def _climb(meshed_nodes: MeshedNodes, sender: str, steps: int) -> None:
    """Have `sender` publish the first `steps` readings of the storm, one after another."""
    for step in range(1, steps + 1):
        _hear_step(meshed_nodes, sender, step)


def _flood_risk(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()["flood_risk"]  # type: ignore[no-any-return]


def _reason_codes(client: TestClient) -> set[str]:
    return {reason["code"] for reason in _flood_risk(client)["reasons"]}


def test_a_calm_day_shows_no_flood_risk(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch", "garage")
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] is None
    assert flood_risk["reasons"] == []
    assert flood_risk["storm_signal"]["on"] is False


def test_the_pressure_drop_raises_the_storm_signal_and_shows_low(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("garage", "creek")
    _climb(meshed_nodes, "garage", 1)
    _climb(meshed_nodes, "creek", 1)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "low"
    assert flood_risk["storm_signal"]["on"] is True
    assert flood_risk["storm_signal"]["nodes"] == 2
    assert flood_risk["storm_signal"]["pressure_hpa"] < 1009
    assert _reason_codes(meshed_nodes["porch"]) == {"pressure_falling"}


def test_the_rain_step_is_elevated_with_rain_and_water_reasons(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek")
    _climb(meshed_nodes, "creek", 2)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "elevated"
    assert {"rain_heavy", "water_high", "water_rising"} <= _reason_codes(meshed_nodes["porch"])


def test_rain_with_water_rising_is_high(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek")
    _climb(meshed_nodes, "creek", 3)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "high"
    assert {"water_high", "rain_heavy"} <= _reason_codes(meshed_nodes["porch"])


def test_reasons_count_the_nodes_that_agree(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("creek")
    meshed_nodes.register("garage", "porch")
    _climb(meshed_nodes, "porch", 3)
    _climb(meshed_nodes, "garage", 3)
    heavy_rain = next(
        reason
        for reason in _flood_risk(meshed_nodes["creek"])["reasons"]
        if reason["code"] == "rain_heavy"
    )
    assert heavy_rain["nodes"] == 2
    assert heavy_rain["value"] >= 25


def test_soil_moisture_rising_at_two_nodes_shows_low(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "garage", "porch")
    for sender in ["creek", "garage"]:
        meshed_nodes.hear_from(sender, soil_pct=30)
        meshed_nodes.hear_from(sender, soil_pct=40)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "low"
    assert _reason_codes(meshed_nodes["porch"]) == {"raining"}


def test_soil_moisture_rising_at_one_of_two_nodes_is_not_raining(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", soil_pct=30)
    meshed_nodes.hear_from("creek", soil_pct=40)
    assert _flood_risk(meshed_nodes["porch"])["level"] is None


def test_a_lone_node_seeing_soil_moisture_rise_is_raining(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek")
    _climb(meshed_nodes, "creek", 2)
    assert "raining" in _reason_codes(meshed_nodes["porch"])


def test_one_low_barometer_among_several_nodes_is_not_a_storm_signal(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("viewer")
    meshed_nodes.register("creek", "garage", "porch")
    for name in ["garage", "creek"]:
        meshed_nodes.hear_from(name)
    _climb(meshed_nodes, "porch", 1)
    assert _flood_risk(meshed_nodes["viewer"])["storm_signal"]["on"] is False


def test_water_that_stays_high_after_the_rain_stops_stays_elevated(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=200)
    meshed_nodes.hear_from("creek", water_cm=450)
    meshed_nodes.advance(121)
    meshed_nodes.hear_from("creek", water_cm=450)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "elevated"
    assert _reason_codes(meshed_nodes["porch"]) == {"water_high"}


def test_after_two_minutes_the_rise_fades_but_the_low_pressure_keeps_the_storm_signal(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek")
    _climb(meshed_nodes, "creek", 3)
    meshed_nodes.advance(121)
    _hear_step(meshed_nodes, "creek", 3)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["storm_signal"]["on"] is True
    assert "water_rising" not in _reason_codes(meshed_nodes["porch"])
    assert "raining" not in _reason_codes(meshed_nodes["porch"])


def test_the_headline_is_the_worst_node_and_each_node_reports_its_own_level(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("viewer")
    meshed_nodes.register("garage", "porch")
    _climb(meshed_nodes, "porch", 3)
    _climb(meshed_nodes, "garage", 2)
    flood_risk = _flood_risk(meshed_nodes["viewer"])
    assert flood_risk["level"] == "high"
    assert flood_risk["nodes"] == {"garage": "elevated", "porch": "high"}


def test_a_node_with_a_single_reading_is_not_rising(meshed_nodes: MeshedNodes) -> None:
    _climb(meshed_nodes, "garage", 3)
    meshed_nodes.advance(121)
    meshed_nodes.start("porch")
    meshed_nodes.register("garage")
    _hear_step(meshed_nodes, "garage", 3)
    codes = _reason_codes(meshed_nodes["porch"])
    assert "water_high" in codes
    assert "water_rising" not in codes


def test_reasons_show_tidy_values(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=290)
    meshed_nodes.hear_from("creek", water_cm=417.3)
    values = [reason["value"] for reason in _flood_risk(meshed_nodes["porch"])["reasons"]]
    assert all(value == round(value, 1) for value in values)


def _surge_reason_of(client: TestClient) -> dict[str, Any] | None:
    return next((r for r in _flood_risk(client)["reasons"] if r["code"] == "water_surge"), None)


def test_a_sudden_rise_makes_the_node_high_with_a_surge_reason(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=20)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from("creek", water_cm=700)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["level"] == "high"
    assert flood_risk["nodes"]["creek"] == "high"
    assert flood_risk["surged"] == ["creek"]
    assert _surge_reason_of(meshed_nodes["porch"]) == {
        "code": "water_surge",
        "nodes": 1,
        "value": 680,
        "seconds": 8,
    }


def test_the_same_rise_spread_over_a_long_time_is_not_a_surge(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=20)
    meshed_nodes.advance(61)
    meshed_nodes.hear_from("creek", water_cm=700)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["surged"] == []
    assert _surge_reason_of(meshed_nodes["porch"]) is None
    assert "water_high" in _reason_codes(meshed_nodes["porch"])


def test_a_rise_just_under_the_surge_size_is_not_a_surge(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("creek", water_cm=10)
    meshed_nodes.hear_from("creek", water_cm=309.9)
    assert _flood_risk(meshed_nodes["porch"])["surged"] == []


def test_a_rise_of_exactly_the_surge_size_is_a_surge(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=10)
    meshed_nodes.hear_from("creek", water_cm=310)
    assert _flood_risk(meshed_nodes["porch"])["surged"] == ["creek"]


def test_a_node_with_a_single_reading_cannot_surge(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("creek", water_cm=700)
    assert _flood_risk(meshed_nodes["porch"])["surged"] == []


def test_only_the_node_that_surged_is_listed_and_the_reason_reports_its_rise(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "garage", "porch")
    for sender in ["creek", "garage"]:
        meshed_nodes.hear_from(sender, water_cm=20)
    meshed_nodes.advance(5)
    meshed_nodes.hear_from("creek", water_cm=500)
    meshed_nodes.hear_from("garage", water_cm=25)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["surged"] == ["creek"]
    assert flood_risk["nodes"] == {"creek": "high", "garage": None, "porch": None}
    surge = _surge_reason_of(meshed_nodes["porch"])
    assert surge is not None and surge["nodes"] == 1 and surge["value"] == 480


def test_the_reason_reports_the_biggest_rise_when_several_nodes_surge(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "garage", "porch")
    for sender in ["creek", "garage"]:
        meshed_nodes.hear_from(sender, water_cm=20)
    meshed_nodes.advance(6)
    meshed_nodes.hear_from("creek", water_cm=450)
    meshed_nodes.hear_from("garage", water_cm=800)
    surge = _surge_reason_of(meshed_nodes["porch"])
    assert surge is not None
    assert (surge["nodes"], surge["value"], surge["seconds"]) == (2, 780, 6)


def test_the_surge_ends_once_the_jump_leaves_the_window_but_the_high_water_stays(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=20)
    meshed_nodes.hear_from("creek", water_cm=700)
    meshed_nodes.advance(61)
    meshed_nodes.hear_from("creek", water_cm=700)
    flood_risk = _flood_risk(meshed_nodes["porch"])
    assert flood_risk["surged"] == []
    assert flood_risk["level"] == "high"
    assert "water_high" in _reason_codes(meshed_nodes["porch"])


def test_the_replays_calm_phase_is_low_with_no_storm_signal(meshed_nodes: MeshedNodes) -> None:
    tracks = {"S0": -12.2, "S1": 3.4, "S2": 14.6, "S3": 54.0}
    meshed_nodes.start_hub()
    for track, river_km in tracks.items():
        meshed_nodes.start_sensor(track.lower(), river_km=river_km)
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    # 12 s is 08:36 on the Event clock, a minute before S0's Surge.
    meshed_nodes.advance(12)
    deadline = time.monotonic() + 5
    while True:
        state = meshed_nodes["hub"].get("/api/state").json()
        heard = {node["id"] for node in state["nodes"]}
        if {track.lower() for track in tracks} <= heard:
            break
        assert time.monotonic() < deadline, "the Sensors were never heard"
        time.sleep(0.01)
    flood_risk = state["flood_risk"]
    assert flood_risk["level"] is None
    assert flood_risk["reasons"] == []
    assert flood_risk["storm_signal"]["on"] is False
    assert set(flood_risk["nodes"].values()) == {None}


def test_no_weather_keyframe_is_below_the_storm_signal_pressure() -> None:
    lowest = min(keyframe.pressure_hpa for keyframe in nepal_event().weather)
    region = load_region(region_path("nepal"))
    assert lowest >= region.rules.flood_warning.storm_pressure.hpa


def test_a_kind_the_rules_do_not_know_is_never_counted(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", also=[Measurement("wind_speed", 400, "km/h")])
    meshed_nodes.hear_from("creek", also=[Measurement("wind_speed", 900, "km/h")])

    assert _flood_risk(meshed_nodes["porch"])["level"] is None
    creek = next(n for n in _nodes(meshed_nodes["porch"]) if n["id"] == "creek")
    assert creek["measurements"]["wind_speed"] == {"value": 900, "unit": "km/h"}


def test_a_known_kind_in_another_unit_is_ignored_and_logged_once_per_node(
    meshed_nodes: MeshedNodes, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    # 900 cm is a High level, but only if it were metres.
    for _ in range(3):
        meshed_nodes.hear_from(
            "creek", leaving_out={"water_level"}, also=[Measurement("water_level", 900, "cm")]
        )

    assert _flood_risk(meshed_nodes["porch"])["level"] is None
    assert caplog.text.count("ignoring water_level from Node creek") == 1


def test_a_node_that_does_not_measure_rain_is_judged_on_what_it_does_measure(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", leaving_out={"rain_rate", "air_pressure"}, water_cm=650)

    assert _flood_risk(meshed_nodes["porch"])["nodes"]["creek"] == "high"


def _nodes(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/state").json()["nodes"]  # type: ignore[no-any-return]
