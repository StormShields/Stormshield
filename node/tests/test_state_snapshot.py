from typing import Any

from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

from storm_shield.community_reading import Measurement


def _state(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/state")
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def _flood_risk(client: TestClient) -> dict[str, Any]:
    return _state(client)["flood_risk"]  # type: ignore[no-any-return]


def _entry(state: dict[str, Any], node: str) -> dict[str, Any]:
    return next(entry for entry in state["nodes"] if entry["id"] == node)


def test_the_state_names_this_node(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    state = _state(meshed_nodes["porch"])
    assert state["id"] == "porch"
    assert state["name"]
    assert state["role"] == "sensor"
    assert state["status"] in {"online", "mesh_only"}


def test_the_state_groups_each_nodes_readings_with_its_own_and_its_peers(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("garage", water_cm=44)
    state = _state(meshed_nodes["porch"])

    assert [entry["id"] for entry in state["nodes"]] == ["garage", "porch"]
    garage = _entry(state, "garage")
    assert garage["simulated"] is True
    assert garage["stale"] is False
    assert garage["age_s"] == 0
    assert len(garage["position"]) == 2
    assert garage["measurements"]["water_level"] == {"value": 0.44, "unit": "m"}
    assert set(garage["measurements"]) == {
        "air_pressure",
        "rain_rate",
        "water_level",
        "soil_moisture",
    }
    assert _entry(state, "porch")["measurements"]["air_pressure"]["unit"] == "hPa"


def test_a_node_entry_holds_exactly_the_kinds_its_sensor_declared(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch", measures="water_level,soil_moisture", river_km=14.6)
    meshed_nodes.hear_from(
        "garage",
        leaving_out={"rain_rate", "air_pressure"},
        also=[Measurement("wind_speed", 7, "km/h")],
    )
    state = _state(meshed_nodes["porch"])

    assert set(_entry(state, "porch")["measurements"]) == {"water_level", "soil_moisture"}
    assert _entry(state, "garage")["measurements"] == {
        "water_level": {"value": 0.2, "unit": "m"},
        "soil_moisture": {"value": 30, "unit": "%"},
        "wind_speed": {"value": 7, "unit": "km/h"},
    }


def test_a_node_that_stops_publishing_turns_stale_after_15_seconds(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("garage")

    meshed_nodes.advance(15)
    assert _entry(_state(meshed_nodes["porch"]), "garage")["stale"] is False

    meshed_nodes.advance(5)
    garage = _entry(_state(meshed_nodes["porch"]), "garage")
    assert garage["stale"] is True
    assert garage["age_s"] == 20

    meshed_nodes.advance(10)
    assert _entry(_state(meshed_nodes["porch"]), "garage")["age_s"] == 30


def test_a_new_reading_makes_a_stale_node_fresh_again(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("garage")
    meshed_nodes.advance(30)
    meshed_nodes.hear_from("garage")
    garage = _entry(_state(meshed_nodes["porch"]), "garage")
    assert garage["stale"] is False
    assert garage["age_s"] == 0


def test_flood_risk_in_the_state_agrees_with_the_readings_beside_it(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek")
    meshed_nodes.hear_from("creek", pressure_hpa=990, water_cm=100, soil_pct=32)
    meshed_nodes.hear_from("creek", pressure_hpa=985, rain_mmh=12, water_cm=350, soil_pct=55)
    state = _state(meshed_nodes["porch"])

    assert _entry(state, "creek")["measurements"]["water_level"]["value"] > 0.3
    assert state["flood_risk"]["level"] == "elevated"
    assert state["flood_risk"]["nodes"] == {"creek": "elevated"}


def test_flood_risk_and_the_node_entries_list_the_same_nodes(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("porch", "garage")
    meshed_nodes.hear_from("garage", rain_mmh=30, water_cm=650)
    state = _state(meshed_nodes["porch"])

    assert _entry(state, "garage")["measurements"]["water_level"]["value"] == 6.5
    assert set(state["flood_risk"]["nodes"]) == {entry["id"] for entry in state["nodes"]}
    assert state["flood_risk"]["nodes"]["garage"] == "high"


def test_a_node_is_stale_only_after_more_than_15_seconds(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("garage")
    meshed_nodes.advance(15.5)
    assert _entry(_state(meshed_nodes["porch"]), "garage")["stale"] is True


def test_only_nodes_that_have_spoken_are_listed_and_none_is_flagged_as_this_node(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    state = _state(meshed_nodes["porch"])
    assert [entry["id"] for entry in state["nodes"]] == ["porch"]
    assert set(state["nodes"][0]) == {
        "id",
        "position",
        "river_km",
        "simulated",
        "age_s",
        "stale",
        "counts",
        "measurements",
        "registered",
        "name",
    }


def test_the_state_holds_exactly_these_keys(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    state = _state(meshed_nodes["porch"])
    assert set(state) == {
        "id",
        "name",
        "role",
        "status",
        "registration",
        "sandbox",
        "region",
        "hazard",
        "flood_risk",
        "live",
        "nodes",
        "official_alerts",
        "community_warnings",
        "official_gauges",
    }


def test_the_state_names_the_region_and_its_hazard(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    state = _state(meshed_nodes["porch"])
    assert state["hazard"] == "flash_flood"
    assert state["region"]["name"] == "nepal"
    assert state["region"]["time_zone"] == "Asia/Kathmandu"
    assert state["region"]["display_units"]["water_level"] == "cm"
    assert {s["tag"]: s["name"] for s in state["region"]["official_alert_sources"]} == {
        "dhm": "DHM",
        "ndrrma": "NDRRMA",
        "district": "District authorities",
    }


def test_the_endpoints_the_state_replaced_are_gone(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    for path in (
        "/api/node",
        "/api/readings",
        "/api/readings/stream",
        "/api/flood-risk",
        "/api/scenario",
    ):
        assert meshed_nodes["porch"].get(path).status_code == 404, path


def test_a_node_silent_for_a_minute_stops_counting_then_drops_off_after_ten(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.register("creek", "porch")
    meshed_nodes.hear_from("creek", water_cm=700)
    meshed_nodes.hear_from("garage")

    meshed_nodes.advance(60)
    creek = _entry(_state(meshed_nodes["porch"]), "creek")
    assert creek["stale"] is True
    assert creek["counts"] is True
    assert _flood_risk(meshed_nodes["porch"])["nodes"]["creek"] == "high"

    meshed_nodes.advance(1)
    assert _entry(_state(meshed_nodes["porch"]), "creek")["counts"] is False
    assert "creek" not in _flood_risk(meshed_nodes["porch"])["nodes"]
    assert _flood_risk(meshed_nodes["porch"])["level"] is None

    meshed_nodes.advance(539)
    assert _entry(_state(meshed_nodes["porch"]), "creek")["counts"] is False
    meshed_nodes.advance(1)
    assert "creek" not in {n["id"] for n in _state(meshed_nodes["porch"])["nodes"]}


def test_a_dropped_node_that_speaks_again_is_listed_and_counts(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.hear_from("garage")
    meshed_nodes.advance(601)
    meshed_nodes.hear_from("garage")
    garage = _entry(_state(meshed_nodes["porch"]), "garage")
    assert garage["counts"] is True
    assert garage["age_s"] == 0


def test_a_node_that_left_goes_stale_then_stops_counting_while_the_others_keep_working(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch", "garage")
    meshed_nodes.remove("garage")
    meshed_nodes.advance(20)
    meshed_nodes.hear_from("shed")
    assert _entry(_state(meshed_nodes["porch"]), "garage")["stale"] is True
    meshed_nodes.advance(45)
    meshed_nodes.hear_from("shed")
    state = _state(meshed_nodes["porch"])
    assert _entry(state, "garage")["counts"] is False
    assert _entry(state, "shed")["counts"] is True
