import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.settings import Settings


def _state(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()  # type: ignore[no-any-return]


def _level(client: TestClient) -> str | None:
    return _state(client)["flood_risk"]["level"]  # type: ignore[no-any-return]


def _registry(meshed_nodes: MeshedNodes) -> dict[str, Any]:
    return meshed_nodes["hub"].get("/api/registry").json()  # type: ignore[no-any-return]


def _row(meshed_nodes: MeshedNodes, node: str) -> dict[str, Any]:
    return next(row for row in _registry(meshed_nodes)["nodes"] if row["id"] == node)


def _push_to_high(meshed_nodes: MeshedNodes, sender: str) -> None:
    meshed_nodes.hear_from(sender, pressure_hpa=990, water_cm=100, soil_pct=32)
    meshed_nodes.hear_from(sender, pressure_hpa=985, rain_mmh=12, water_cm=350, soil_pct=55)
    meshed_nodes.hear_from(sender, pressure_hpa=980, rain_mmh=30, water_cm=390, soil_pct=85)


def _accept(meshed_nodes: MeshedNodes, node: str) -> Any:
    return meshed_nodes["hub"].post("/api/registry/accept", json={"id": node})


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def test_an_unverified_node_pushed_to_high_does_not_change_flood_risk_until_it_is_registered(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.start_hub()
    meshed_nodes["porch"].post("/api/registry/signup")
    _accept(meshed_nodes, "porch")

    _push_to_high(meshed_nodes, "garage")
    assert _level(meshed_nodes["porch"]) is None
    garage = next(n for n in _state(meshed_nodes["porch"])["nodes"] if n["id"] == "garage")
    assert garage["registered"] is False

    meshed_nodes.announce_sign_up("garage", "garage")
    assert _accept(meshed_nodes, "garage").status_code == 200

    assert _level(meshed_nodes["porch"]) == "high"
    assert _state(meshed_nodes["porch"])["flood_risk"]["nodes"]["garage"] == "high"


def test_before_any_registry_arrives_nothing_counts(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    _push_to_high(meshed_nodes, "creek")
    state = _state(meshed_nodes["porch"])
    assert state["flood_risk"]["level"] is None
    assert state["flood_risk"]["nodes"] == {}
    assert state["nodes"][0]["registered"] is False


def test_a_node_goes_from_unverified_to_waiting_to_registered(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.start_hub()
    assert _state(meshed_nodes["porch"])["registration"] == "unverified"

    answer = meshed_nodes["porch"].post("/api/registry/signup")
    assert answer.json() == {"registration": "waiting"}
    assert _state(meshed_nodes["porch"])["registration"] == "waiting"
    assert _row(meshed_nodes, "porch")["status"] == "waiting"

    _accept(meshed_nodes, "porch")
    assert _state(meshed_nodes["porch"])["registration"] == "registered"


def test_a_registered_node_shows_its_registry_name_and_an_unverified_one_has_none(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.announce_registry(1, ["garage"])
    meshed_nodes.hear_from("garage")
    meshed_nodes.hear_from("stranger")
    names = {n["id"]: n["name"] for n in _state(meshed_nodes["porch"])["nodes"]}
    assert names["garage"] == "garage"
    assert names["stranger"] is None


@pytest.mark.usefixtures("nepal_region")
def test_the_hub_is_always_registered_and_counts_itself(meshed_nodes: MeshedNodes) -> None:
    # At the end of the replay the gauge at the Hub's River km reads 7.5 m.
    meshed_nodes.start_hub(river_km=-12.2, publish_every_seconds=0.02)
    meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "end"})
    _wait_until(lambda: _level(meshed_nodes["hub"]) == "high")
    assert _state(meshed_nodes["hub"])["registration"] == "registered"


def test_a_sign_up_is_sent_again_until_the_hub_has_accepted_it(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_sensor("porch", sign_up_repeat_seconds=0.02)
    meshed_nodes.start_hub()
    meshed_nodes["porch"].post("/api/registry/signup")

    # A restarted Hub forgets the waiting Sign-up; the Node's repeat brings it back.
    meshed_nodes.stop_hub()
    meshed_nodes.start_hub()
    _wait_until(lambda: _row_status(meshed_nodes, "porch") == "waiting")

    _accept(meshed_nodes, "porch")
    assert _state(meshed_nodes["porch"])["registration"] == "registered"


def _row_status(meshed_nodes: MeshedNodes, node: str) -> str | None:
    rows = [row for row in _registry(meshed_nodes)["nodes"] if row["id"] == node]
    return rows[0]["status"] if rows else None


def test_a_registry_with_a_lower_ver_is_ignored(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.announce_registry(5, ["porch"])
    meshed_nodes.announce_registry(4, [])
    assert _state(meshed_nodes["porch"])["registration"] == "registered"


def test_a_registry_that_does_not_come_from_the_hub_is_ignored(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.announce_registry(1, ["porch"], sender="intruder")
    assert _state(meshed_nodes["porch"])["registration"] == "unverified"


def test_a_registry_that_spans_several_packets_is_ignored(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.announce_registry(1, ["porch"], of=2)
    assert _state(meshed_nodes["porch"])["registration"] == "unverified"


def test_a_sign_up_that_names_another_node_is_dropped(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.announce_sign_up("garage", "garage")
    forged = b'{"v":1,"kind":"signup","node":"porch","name":"porch"}'
    meshed_nodes.send_bytes(forged, sender="garage")
    statuses = {row["id"]: row["status"] for row in _registry(meshed_nodes)["nodes"]}
    assert statuses == {"hub": "registered", "garage": "waiting"}


def test_the_registry_lists_registered_waiting_and_unverified_nodes(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.start_hub()
    meshed_nodes.announce_sign_up("garage", "the garage")
    meshed_nodes.hear_from("stranger")
    meshed_nodes["porch"].post("/api/registry/signup")
    _accept(meshed_nodes, "porch")
    meshed_nodes.advance(7)

    rows = {row["id"]: row for row in _registry(meshed_nodes)["nodes"]}
    assert rows["hub"]["status"] == "registered"
    assert rows["porch"]["status"] == "registered"
    assert rows["porch"]["name"] == "porch"
    assert rows["garage"]["status"] == "waiting"
    assert rows["garage"]["name"] == "the garage"
    assert rows["garage"]["last_heard_s"] == 7
    assert rows["stranger"]["status"] == "unverified"
    assert rows["stranger"]["name"] is None
    assert rows["stranger"]["last_heard_s"] == 7


def test_accepting_a_node_that_is_not_waiting_answers_404(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    assert _accept(meshed_nodes, "nobody").status_code == 404
    assert _accept(meshed_nodes, "hub").status_code == 404


def test_an_accept_that_would_not_fit_one_packet_answers_409_and_changes_nothing(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    for number in range(12):
        meshed_nodes.announce_sign_up(f"node{number:08}", "n" * 32)
    answers = [_accept(meshed_nodes, f"node{number:08}").status_code for number in range(12)]
    first_refused = answers.index(409)
    assert first_refused > 1
    assert answers[:first_refused] == [200] * first_refused
    ver_after_refusal = _registry(meshed_nodes)["ver"]
    assert _accept(meshed_nodes, f"node{first_refused:08}").status_code == 409
    assert _registry(meshed_nodes)["ver"] == ver_after_refusal
    registered = [r for r in _registry(meshed_nodes)["nodes"] if r["status"] == "registered"]
    assert len(registered) == first_refused + 1


def test_a_sensor_has_neither_hub_registry_route(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    assert meshed_nodes["porch"].get("/api/registry").status_code == 404
    assert meshed_nodes["porch"].post("/api/registry/accept", json={"id": "x"}).status_code == 404


def test_a_restarted_hub_keeps_its_nodes_and_announces_a_higher_ver(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.start_hub()
    meshed_nodes["porch"].post("/api/registry/signup")
    _accept(meshed_nodes, "porch")
    ver_before = _registry(meshed_nodes)["ver"]

    meshed_nodes.stop_hub()
    meshed_nodes.start_hub()

    assert _registry(meshed_nodes)["ver"] == ver_before + 1
    assert _row_status(meshed_nodes, "porch") == "registered"
    assert _state(meshed_nodes["porch"])["registration"] == "registered"


def test_a_hub_whose_registry_file_is_unreadable_refuses_to_start(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "registry.json").write_text("not json")
    settings = Settings(
        name="hub", role="hub", data_dir=data_dir, dashboard_dir=tmp_path / "no-dashboard"
    )
    with pytest.raises(RuntimeError, match="registry.json"):
        create_app(settings, InMemoryNetwork().join("hub", "hub"))


def test_a_sensor_that_serves_the_dashboard_still_answers_404_on_the_hub_routes(
    tmp_path: Path,
) -> None:
    dashboard = tmp_path / "dist"
    dashboard.mkdir()
    (dashboard / "index.html").write_text("<html></html>")
    settings = Settings(
        name="porch", data_dir=tmp_path / "data", dashboard_dir=dashboard, hub_identity="hub"
    )
    client = TestClient(create_app(settings, InMemoryNetwork().join("porch", "hub")))
    assert client.get("/api/registry").status_code == 404
    assert client.post("/api/registry/accept", json={"id": "x"}).status_code == 404


def test_a_hub_that_starts_over_without_its_file_still_beats_the_ver_nodes_hold(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.start_hub()
    meshed_nodes["porch"].post("/api/registry/signup")
    _accept(meshed_nodes, "porch")
    meshed_nodes.stop_hub()
    (meshed_nodes.data_dir("hub") / "registry.json").unlink()
    meshed_nodes.advance(60)

    meshed_nodes.start_hub()

    assert _state(meshed_nodes["porch"])["registration"] != "registered"
    assert _registry(meshed_nodes)["ver"] > 1_000_000_000
