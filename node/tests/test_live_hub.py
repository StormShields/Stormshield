from typing import Any

from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

from storm_shield.timing import STALE_AFTER_SECONDS

RIVER_KM = -12.2


def _state(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()  # type: ignore[no-any-return]


def _listed(client: TestClient) -> list[str]:
    """The Nodes listed, leaving out the Hub, whose own reading is simulated too."""
    return [node["id"] for node in _state(client)["nodes"] if node["id"] != "hub"]


def _register(meshed_nodes: MeshedNodes, *nodes: str) -> None:
    for node in nodes:
        meshed_nodes.announce_sign_up(node, node)
        assert (
            meshed_nodes["hub"].post("/api/registry/accept", json={"id": node}).status_code == 200
        )


def _surge(meshed_nodes: MeshedNodes, node: str) -> None:
    meshed_nodes.hear_from(node, water_cm=20, river_km=RIVER_KM)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from(node, water_cm=340, river_km=RIVER_KM)


def _warnings(meshed_nodes: MeshedNodes) -> list[dict[str, Any]]:
    return meshed_nodes["hub"].get("/api/warnings").json()["warnings"]  # type: ignore[no-any-return]


def test_a_hub_with_only_simulated_nodes_is_not_live(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim")
    meshed_nodes.hear_from("sim")

    state = _state(meshed_nodes["hub"])
    assert state["live"] is False
    assert _listed(meshed_nodes["hub"]) == ["sim"]


def test_a_registered_real_reading_makes_the_hub_live_and_hides_simulated_nodes(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim", "real")
    meshed_nodes.hear_from("sim")
    meshed_nodes.hear_from("real", simulated=False)

    state = _state(meshed_nodes["hub"])
    assert state["live"] is True
    assert _listed(meshed_nodes["hub"]) == ["real"]


def test_a_sensor_agrees_with_the_hub_about_live_and_the_nodes_listed(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    assert meshed_nodes["porch"].post("/api/registry/signup").status_code == 200
    assert meshed_nodes["hub"].post("/api/registry/accept", json={"id": "porch"}).status_code == 200
    _register(meshed_nodes, "sim", "real")
    meshed_nodes.hear_from("sim")
    meshed_nodes.hear_from("real", simulated=False)

    assert _state(meshed_nodes["porch"])["live"] is True
    assert _listed(meshed_nodes["porch"]) == _listed(meshed_nodes["hub"]) == ["real"]


def test_an_unverified_nodes_real_reading_does_not_make_the_hub_live(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim")
    meshed_nodes.hear_from("sim")
    meshed_nodes.hear_from("stranger", simulated=False)

    assert _state(meshed_nodes["hub"])["live"] is False
    assert "sim" in _listed(meshed_nodes["hub"])


def test_a_surging_simulated_node_changes_nothing_while_the_hub_is_live(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim", "real")
    meshed_nodes.hear_from("real", simulated=False)

    _surge(meshed_nodes, "sim")
    meshed_nodes.hear_from("real", simulated=False)

    state = _state(meshed_nodes["hub"])
    assert state["flood_risk"]["surged"] == []
    assert state["flood_risk"]["level"] is None
    assert _warnings(meshed_nodes) == []


def test_a_surging_real_node_still_raises_flood_risk_and_a_warning(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "real")
    meshed_nodes.hear_from("real", water_cm=20, river_km=RIVER_KM, simulated=False)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from("real", water_cm=340, river_km=RIVER_KM, simulated=False)

    assert _state(meshed_nodes["hub"])["flood_risk"]["surged"] == ["real"]
    assert len(_warnings(meshed_nodes)) == 1


def test_a_warning_issued_before_the_hub_went_live_stays_in_the_log(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim", "real")
    _surge(meshed_nodes, "sim")
    assert len(_warnings(meshed_nodes)) == 1

    meshed_nodes.hear_from("real", simulated=False)

    assert _state(meshed_nodes["hub"])["live"] is True
    assert len(_warnings(meshed_nodes)) == 1


def test_the_hub_stops_being_live_once_the_real_node_goes_stale(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "sim", "real")
    meshed_nodes.hear_from("real", simulated=False)
    meshed_nodes.advance(STALE_AFTER_SECONDS - 1)
    meshed_nodes.hear_from("sim")
    assert _state(meshed_nodes["hub"])["live"] is True

    meshed_nodes.advance(2)
    meshed_nodes.hear_from("sim")

    state = _state(meshed_nodes["hub"])
    assert state["live"] is False
    assert _listed(meshed_nodes["hub"]) == ["real", "sim"]


def _replay(client: TestClient) -> dict[str, Any]:
    return client.get("/api/replay").json()  # type: ignore[no-any-return]


def _go_live(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "real")
    meshed_nodes.hear_from("real", simulated=False)


def test_a_live_hub_refuses_to_start_resume_reset_or_jump(meshed_nodes: MeshedNodes) -> None:
    _go_live(meshed_nodes)
    hub = meshed_nodes["hub"]
    phase = hub.get("/api/replay/phases").json()["phases"][0]["id"]

    for path, body in [
        ("/api/replay/start", None),
        ("/api/replay/resume", None),
        ("/api/replay/reset", None),
        ("/api/replay/jump", {"phase": phase}),
    ]:
        answer = hub.post(path, json=body)
        assert answer.status_code == 409, path
        assert answer.json()["detail"] == "live Sensors are reporting, so no Replay can play"
    assert _replay(hub)["state"] == "stopped"


def test_a_live_hub_still_lists_events_allows_a_rate_change_and_refuses_pause(
    meshed_nodes: MeshedNodes,
) -> None:
    _go_live(meshed_nodes)
    hub = meshed_nodes["hub"]

    assert hub.get("/api/replay/events").json()["events"]
    assert hub.post("/api/replay/rate", json={"rate": 10}).status_code == 200
    assert hub.post("/api/replay/pause").status_code == 409


def test_a_playing_replay_stops_on_every_node_when_the_first_real_reading_arrives(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "real")
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    assert _replay(meshed_nodes["porch"])["state"] == "playing"

    meshed_nodes.hear_from("real", simulated=False)

    assert _replay(meshed_nodes["hub"])["state"] == "stopped"
    assert _replay(meshed_nodes["porch"])["state"] == "stopped"


def test_a_paused_replay_stops_the_same_way(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "real")
    assert meshed_nodes["hub"].post("/api/replay/reset").status_code == 200
    assert _replay(meshed_nodes["porch"])["state"] == "paused"

    meshed_nodes.hear_from("real", simulated=False)

    assert _replay(meshed_nodes["hub"])["state"] == "stopped"
    assert _replay(meshed_nodes["porch"])["state"] == "stopped"


def test_start_works_again_once_the_last_real_node_goes_stale(meshed_nodes: MeshedNodes) -> None:
    _go_live(meshed_nodes)
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 409

    meshed_nodes.advance(STALE_AFTER_SECONDS + 1)

    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    assert _replay(meshed_nodes["hub"])["state"] == "playing"
