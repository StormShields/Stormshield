import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

from storm_shield.community_warning import (
    CommunityWarning,
    HeardCommunityWarnings,
    MeasuredSpeed,
)
from storm_shield.replay import ReplayClockMessage

pytestmark = pytest.mark.usefixtures("nepal_region")

S0_RIVER_KM = -12.2


def _warnings_shown_on(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/state").json()["community_warnings"]  # type: ignore[no-any-return]


def _warning_log(meshed_nodes: MeshedNodes) -> list[dict[str, Any]]:
    return meshed_nodes["hub"].get("/api/warnings").json()["warnings"]  # type: ignore[no-any-return]


def _register(meshed_nodes: MeshedNodes, node: str) -> None:
    meshed_nodes.announce_sign_up(node, node)
    assert meshed_nodes["hub"].post("/api/registry/accept", json={"id": node}).status_code == 200


def _surge(meshed_nodes: MeshedNodes, node: str, river_km: float | None = S0_RIVER_KM) -> None:
    meshed_nodes.hear_from(node, water_cm=20, river_km=river_km)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from(node, water_cm=340, river_km=river_km)


def test_a_registered_nodes_surge_makes_the_hub_send_one_warning_every_node_shows(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "s0")

    _surge(meshed_nodes, "s0")

    expected = {
        "kind": "warning",
        "nodes": ["s0"],
        "reasons": ["water_surge"],
        "origin": "s0",
        "origin_km": S0_RIVER_KM,
    }
    for client in (meshed_nodes["porch"], meshed_nodes["hub"]):
        shown = _warnings_shown_on(client)
        assert len(shown) == 1
        assert expected.items() <= shown[0].items()
    assert len(_warning_log(meshed_nodes)) == 1


def test_the_warning_carries_the_event_time_of_the_surge(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    meshed_nodes["hub"].post("/api/replay/start")

    _surge(meshed_nodes, "s0")

    event_t = meshed_nodes["hub"].get("/api/replay").json()["event_t"]
    assert _warning_log(meshed_nodes)[0]["surge_t"] == event_t


def test_an_unverified_nodes_surge_makes_no_warning(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")

    _surge(meshed_nodes, "stranger")

    assert _warning_log(meshed_nodes) == []
    assert _warnings_shown_on(meshed_nodes["porch"]) == []


def test_a_surging_node_with_no_river_km_makes_no_warning(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")

    _surge(meshed_nodes, "s0", river_km=None)

    assert _warning_log(meshed_nodes) == []


def test_no_second_warning_while_the_same_surge_holds(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    _surge(meshed_nodes, "s0")

    meshed_nodes.advance(10)
    meshed_nodes.hear_from("s0", water_cm=350, river_km=S0_RIVER_KM)
    meshed_nodes.advance(10)
    meshed_nodes.hear_from("s0", water_cm=360, river_km=S0_RIVER_KM)

    assert len(_warning_log(meshed_nodes)) == 1


def test_a_new_surge_after_the_first_has_passed_makes_a_new_warning(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    _surge(meshed_nodes, "s0")
    meshed_nodes.advance(200)
    meshed_nodes.hear_from("s0", water_cm=20, river_km=S0_RIVER_KM)

    _surge(meshed_nodes, "s0")

    log = _warning_log(meshed_nodes)
    assert len(log) == 2
    assert log[0]["id"] > log[1]["id"]


def test_two_nodes_surging_make_one_warning_each(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")

    _surge(meshed_nodes, "s0", river_km=-12.2)
    _surge(meshed_nodes, "s1", river_km=3.6)

    assert sorted(w["origin"] for w in _warning_log(meshed_nodes)) == ["s0", "s1"]


def test_a_warning_not_sent_by_the_hub_is_not_shown(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    forged = CommunityWarning(
        id=1,
        t=1,
        hazard="flash_flood",
        nodes=["s0"],
        reasons=["water_surge"],
        origin="s0",
        origin_km=S0_RIVER_KM,
        surge_t=1,
    )

    meshed_nodes.announce_community_warning(forged, sender="rogue")

    assert _warnings_shown_on(meshed_nodes["porch"]) == []


def test_a_replay_reset_hides_a_warning_the_replay_has_not_reached_again(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "s0")
    meshed_nodes["hub"].post("/api/replay/start")
    _surge(meshed_nodes, "s0")
    assert len(_warnings_shown_on(meshed_nodes["porch"])) == 1

    meshed_nodes["hub"].post("/api/replay/reset")

    assert _warnings_shown_on(meshed_nodes["porch"]) == []
    assert len(_warning_log(meshed_nodes)) == 1


def test_a_sensor_has_no_warning_log(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    assert meshed_nodes["porch"].get("/api/warnings").status_code == 404


def test_a_node_that_joins_after_the_warning_gets_it_from_the_hubs_repeat(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub(warning_repeat_seconds=0.02)
    _register(meshed_nodes, "s0")
    _surge(meshed_nodes, "s0")

    meshed_nodes.start("latecomer")

    deadline = time.monotonic() + 5
    while not _warnings_shown_on(meshed_nodes["latecomer"]):
        assert time.monotonic() < deadline, "the repeat never reached the late Node"
        time.sleep(0.01)
    assert len(_warnings_shown_on(meshed_nodes["latecomer"])) == 1


def test_a_replay_run_again_shows_one_card_per_node(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "s0")
    meshed_nodes["hub"].post("/api/replay/start")
    _surge(meshed_nodes, "s0")
    meshed_nodes["hub"].post("/api/replay/reset")
    meshed_nodes.advance(200)
    meshed_nodes.hear_from("s0", water_cm=20, river_km=S0_RIVER_KM)

    meshed_nodes["hub"].post("/api/replay/start")
    _surge(meshed_nodes, "s0")

    assert len(_warning_log(meshed_nodes)) == 2
    assert len(_warnings_shown_on(meshed_nodes["porch"])) == 1


def _surge_after(meshed_nodes: MeshedNodes, node: str, river_km: float, minutes: float) -> None:
    meshed_nodes.advance(minutes * 60)
    _surge(meshed_nodes, node, river_km=river_km)


def test_a_second_nodes_surge_updates_the_warning_with_the_measured_speed(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")
    _surge(meshed_nodes, "s0", river_km=0.0)
    first = _warning_log(meshed_nodes)[0]

    # _surge adds 8 s between its readings, so 12 min minus 8 s makes the Surges 12 min apart:
    # 15.6 km in 12 min is 78 km/h.
    _surge_after(meshed_nodes, "s1", river_km=15.6, minutes=12 - 8 / 60)

    for shown in (_warning_log(meshed_nodes), _warnings_shown_on(meshed_nodes["porch"])):
        assert len(shown) == 1
        assert shown[0]["id"] == first["id"]
        assert shown[0]["origin"] == "s0"
        measured = shown[0]["measured"]
        assert (measured["node"], measured["km"]) == ("s1", 15.6)
        assert measured["speed_kmh"] == 78.0
        assert measured["surge_t"] - shown[0]["surge_t"] == 12 * 60


def test_a_surge_upstream_of_the_origin_is_not_a_measurement(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")
    _surge(meshed_nodes, "s1", river_km=15.6)

    _surge_after(meshed_nodes, "s0", river_km=0.0, minutes=12)

    log = _warning_log(meshed_nodes)
    assert len(log) == 2
    assert all(warning["measured"] is None for warning in log)


def test_an_impossible_speed_is_not_a_measurement(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")
    _surge(meshed_nodes, "s0", river_km=0.0)

    # 15.6 km in about a minute is over 800 km/h.
    _surge_after(meshed_nodes, "s1", river_km=15.6, minutes=1)

    log = _warning_log(meshed_nodes)
    assert len(log) == 2
    assert all(warning["measured"] is None for warning in log)


def test_a_third_node_does_not_refine_the_measurement(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    for node in ("s0", "s1", "s2"):
        _register(meshed_nodes, node)
    _surge(meshed_nodes, "s0", river_km=0.0)
    _surge_after(meshed_nodes, "s1", river_km=15.6, minutes=12)
    measured = _warning_log(meshed_nodes)[0]["measured"]

    _surge_after(meshed_nodes, "s2", river_km=40.0, minutes=20)

    log = _warning_log(meshed_nodes)
    assert [warning["origin"] for warning in log] == ["s2", "s0"]
    assert log[1]["measured"] == measured


def test_the_measurement_shows_only_once_the_event_clock_reaches_the_second_surge(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")
    meshed_nodes["hub"].post("/api/replay/start")
    # 32 s of real time is 16 min of event time: 20 km at 75 km/h.
    _surge(meshed_nodes, "s0", river_km=0.0)
    _surge_after(meshed_nodes, "s1", river_km=20.0, minutes=24 / 60)
    assert _warnings_shown_on(meshed_nodes["porch"])[0]["measured"]["speed_kmh"] == 75.0

    # 08:37 is after the origin's Surge (about 08:34) and before the second's (about 08:50).
    meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "collapse"})

    shown = _warnings_shown_on(meshed_nodes["porch"])
    assert len(shown) == 1
    assert shown[0]["measured"] is None


def test_an_older_copy_of_a_warning_does_not_undo_its_measurement() -> None:
    heard = HeardCommunityWarnings()
    plain = CommunityWarning(
        id=7,
        t=1,
        hazard="flash_flood",
        nodes=["s0"],
        reasons=["water_surge"],
        origin="s0",
        origin_km=0.0,
        surge_t=1,
    )
    measured = plain.model_copy(
        update={"measured": MeasuredSpeed(node="s1", km=15.6, surge_t=721, speed_kmh=78.0)}
    )

    heard.hear(measured)
    heard.hear(plain)

    assert heard.shown_at(
        ReplayClockMessage(event="bhote-koshi-2026", state="stopped", event_t=0, rate=30)
    ) == [measured]
