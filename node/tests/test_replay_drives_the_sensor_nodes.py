import time
from collections.abc import Callable
from functools import partial
from typing import Any

import pytest
from meshed_nodes import MeshedNodes

from storm_shield.timing import REPLAY_PUBLISH_EVERY_SECONDS

pytestmark = pytest.mark.usefixtures("nepal_region")

# 08:30 NPT on 26 Aug 2026, the first moment of the replay timeline.
REPLAY_START = 1787712300
RATE = 30
# Where the Event file puts its four gauges, in River km.
S0_KM, S1_KM, S2_KM, S3_KM = -12.2, 3.4, 14.6, 54.0
STATION_KM = {"S0": S0_KM, "S1": S1_KM, "S2": S2_KM, "S3": S3_KM}


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _event_clock(meshed_nodes: MeshedNodes, name: str) -> dict[str, object]:
    clock: dict[str, object] = meshed_nodes[name].get("/api/replay").json()
    return clock


def _heard_from(meshed_nodes: MeshedNodes, viewer: str, node: str) -> dict[str, Any]:
    nodes = meshed_nodes[viewer].get("/api/state").json()["nodes"]
    entry: dict[str, Any] = next(entry for entry in nodes if entry["id"] == node)
    return entry


def _water_cm(meshed_nodes: MeshedNodes, viewer: str, node: str) -> float:
    water_m: float = _heard_from(meshed_nodes, viewer, node)["measurements"]["water_level"]["value"]
    return round(water_m * 100, 1)


def _start_replay(meshed_nodes: MeshedNodes) -> None:
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200


def test_a_replay_started_on_the_hub_reaches_every_node(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    for name in ("hub", "s0", "porch"):
        assert _event_clock(meshed_nodes, name) == {
            "v": 2,
            "kind": "replay",
            "event": "bhote-koshi-2026",
            "state": "playing",
            "event_t": REPLAY_START,
            "rate": RATE,
        }


def test_every_node_counts_the_event_clock_on_its_own_clock(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    meshed_nodes.advance(60)
    for name in ("hub", "porch"):
        assert _event_clock(meshed_nodes, name)["event_t"] == REPLAY_START + 60 * RATE


def test_a_sensors_readings_follow_the_surface_at_its_river_km(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s2", river_km=14.6)
    _start_replay(meshed_nodes)
    # 20 s later the Event clock reads 08:40, where Syabrubesi's gauge read 1.62 m.
    meshed_nodes.advance(20)
    _wait_until(lambda: _water_cm(meshed_nodes, "s2", "s2") == 162.0)
    assert _water_cm(meshed_nodes, "hub", "s2") == 162.0


def test_a_sensor_shows_the_surge_its_track_holds(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    _start_replay(meshed_nodes)
    # 08:37:30 is 450 event seconds in, and S0's water has jumped from 0.7 m to 4.2 m.
    meshed_nodes.advance(15)
    _wait_until(lambda: _water_cm(meshed_nodes, "s0", "s0") == 420.0)


def test_sensors_at_different_positions_read_different_levels(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("up", river_km=S0_KM)
    meshed_nodes.start_sensor("down", river_km=S2_KM)
    # In the middle of the second reach: S1 (3.4 km) reads 0.9 m and S2 (14.6 km) reads 1.62 m now.
    meshed_nodes.start_sensor("between", river_km=(S1_KM + S2_KM) / 2)
    _start_replay(meshed_nodes)
    meshed_nodes.advance(20)
    _wait_until(lambda: _water_cm(meshed_nodes, "hub", "up") == 750.0)
    _wait_until(lambda: _water_cm(meshed_nodes, "hub", "down") == 162.0)
    _wait_until(lambda: _water_cm(meshed_nodes, "hub", "between") == pytest.approx(126, abs=1))


@pytest.mark.parametrize("river_km", [None, S0_KM - 0.1, S3_KM + 0.1])
def test_a_sensor_outside_the_corridor_sends_no_water_level(
    meshed_nodes: MeshedNodes, river_km: float | None
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("dry", river_km=river_km)
    meshed_nodes.start_sensor("wet", river_km=S2_KM)
    _start_replay(meshed_nodes)
    meshed_nodes.advance(20)
    _wait_until(lambda: _water_cm(meshed_nodes, "hub", "wet") == 162.0)
    _wait_until(
        lambda: "dry" in {n["id"] for n in meshed_nodes["hub"].get("/api/state").json()["nodes"]}
    )
    dry = _heard_from(meshed_nodes, "hub", "dry")["measurements"]
    assert "water_level" not in dry
    assert {"rain_rate", "soil_moisture", "air_pressure"} <= dry.keys()


def test_a_sensor_reads_the_events_weather(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    # 08:30 is the first moment: 3 mm/h of rain, 80 % soil moisture and 1005 hPa.
    _wait_until(
        lambda: _heard_from(meshed_nodes, "hub", "porch")["measurements"]["rain_rate"]["value"] == 3
    )
    measurements = _heard_from(meshed_nodes, "hub", "porch")["measurements"]
    assert measurements["rain_rate"]["value"] == 3
    assert measurements["soil_moisture"]["value"] == 80
    assert measurements["air_pressure"]["value"] == 1005


def test_a_node_with_the_clock_stopped_reads_the_events_first_moment(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch", river_km=S2_KM)
    _wait_until(lambda: _water_cm(meshed_nodes, "porch", "porch") == 150.0)


def test_a_replay_message_not_from_the_hub_is_ignored(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    meshed_nodes.announce_replay("playing", REPLAY_START, sender="intruder")
    assert _event_clock(meshed_nodes, "s0")["state"] == "stopped"


def test_a_sensor_cannot_start_the_replay(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    assert meshed_nodes["s0"].post("/api/replay/start").status_code == 404


def test_a_node_that_joins_late_converges_after_a_repeat(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(replay_repeat_seconds=0.02)
    _start_replay(meshed_nodes)
    meshed_nodes.advance(10)
    meshed_nodes.start_sensor("late", river_km=3.4)
    _wait_until(lambda: _event_clock(meshed_nodes, "late")["state"] == "playing")
    assert _event_clock(meshed_nodes, "late")["event_t"] == REPLAY_START + 10 * RATE


def test_pausing_the_replay_holds_every_nodes_readings(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s2", river_km=14.6)
    _start_replay(meshed_nodes)
    meshed_nodes.advance(20)
    assert meshed_nodes["hub"].post("/api/replay/pause").json()["state"] == "paused"
    held = REPLAY_START + 20 * RATE
    meshed_nodes.advance(60)
    for name in ("hub", "s2"):
        clock = _event_clock(meshed_nodes, name)
        assert (clock["state"], clock["event_t"]) == ("paused", held)
    _wait_until(lambda: _water_cm(meshed_nodes, "s2", "s2") == 162.0)
    assert meshed_nodes["hub"].post("/api/replay/resume").json()["state"] == "playing"
    meshed_nodes.advance(10)
    assert _event_clock(meshed_nodes, "s2")["event_t"] == held + 10 * RATE


def test_jumping_to_a_phase_moves_every_nodes_event_clock(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    jump = meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "dhm-sms"})
    assert jump.status_code == 200
    # DHM SMS is 09:15, 45 minutes after the replay starts.
    for name in ("hub", "porch"):
        clock = _event_clock(meshed_nodes, name)
        assert (clock["state"], clock["event_t"]) == ("playing", REPLAY_START + 45 * 60)


def test_jumping_while_paused_stays_paused(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _start_replay(meshed_nodes)
    meshed_nodes["hub"].post("/api/replay/pause")
    meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "border"})
    clock = _event_clock(meshed_nodes, "hub")
    assert (clock["state"], clock["event_t"]) == ("paused", REPLAY_START + 10 * 60)


def _is_at_rate(meshed_nodes: MeshedNodes, name: str, rate: int) -> bool:
    return _event_clock(meshed_nodes, name)["rate"] == rate


def test_changing_the_rate_while_playing_reaches_every_node_without_moving_the_clock(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    meshed_nodes.advance(10)
    assert meshed_nodes["hub"].post("/api/replay/rate", json={"rate": 5}).status_code == 200
    for name in ("hub", "porch"):
        _wait_until(partial(_is_at_rate, meshed_nodes, name, 5))
        clock = _event_clock(meshed_nodes, name)
        assert (clock["state"], clock["event_t"]) == ("playing", REPLAY_START + 10 * 30)
    meshed_nodes.advance(10)
    assert _event_clock(meshed_nodes, "hub")["event_t"] == REPLAY_START + 10 * 30 + 10 * 5


def test_a_rate_chosen_before_start_is_the_rate_the_replay_starts_at(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    assert meshed_nodes["hub"].post("/api/replay/rate", json={"rate": 10}).status_code == 200
    assert _event_clock(meshed_nodes, "hub")["state"] == "stopped"
    _start_replay(meshed_nodes)
    assert _event_clock(meshed_nodes, "hub")["rate"] == 10
    meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "border"})
    assert _event_clock(meshed_nodes, "hub")["rate"] == 10


def test_a_rate_too_slow_for_the_surge_is_refused(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    assert meshed_nodes["hub"].post("/api/replay/rate", json={"rate": 1}).status_code == 422


def test_jumping_to_an_unknown_phase_is_refused(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    assert meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "nope"}).status_code == 422


def test_pause_and_resume_refuse_the_wrong_state(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    assert meshed_nodes["hub"].post("/api/replay/pause").status_code == 409
    assert meshed_nodes["hub"].post("/api/replay/resume").status_code == 409


def test_reset_returns_every_node_to_calm(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    _start_replay(meshed_nodes)
    meshed_nodes.advance(15)
    _wait_until(lambda: _water_cm(meshed_nodes, "s0", "s0") == 420.0)
    assert meshed_nodes["hub"].post("/api/replay/reset").status_code == 200
    for name in ("hub", "s0"):
        clock = _event_clock(meshed_nodes, name)
        assert (clock["state"], clock["event_t"]) == ("paused", REPLAY_START)
    _wait_until(lambda: _water_cm(meshed_nodes, "hub", "s0") < 100)


def test_the_phases_and_the_internet_cue_are_listed_in_event_time(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    listed = meshed_nodes["hub"].get("/api/replay/phases").json()
    assert [phase["id"] for phase in listed["phases"]] == [
        "calm",
        "collapse",
        "border",
        "syabrubesi",
        "dhm-notice",
        "dhm-sms",
        "betrawati",
        "end",
    ]
    assert listed["phases"][0]["event_t"] == REPLAY_START
    assert listed["internet_cue_event_t"] == REPLAY_START + 50 * 60


def test_a_sensor_cannot_control_the_replay(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    for action in ("pause", "resume", "reset"):
        assert meshed_nodes["s0"].post(f"/api/replay/{action}").status_code == 404


# 10:30 NPT, just after the last Official Alert (10:28), where the Hub stops the replay.
REPLAY_END = REPLAY_START + 2 * 3600


def _wait_until_paused_at(meshed_nodes: MeshedNodes, name: str, event_t: int) -> None:
    _wait_until(
        lambda: (
            _event_clock(meshed_nodes, name)["state"] == "paused"
            and _event_clock(meshed_nodes, name)["event_t"] == event_t
        )
    )


def test_the_replay_stops_at_its_end_on_every_node(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    _start_replay(meshed_nodes)
    meshed_nodes.advance((REPLAY_END - REPLAY_START) / RATE + 30)
    for name in ("hub", "porch"):
        _wait_until_paused_at(meshed_nodes, name, REPLAY_END)
    alerts = meshed_nodes["porch"].get("/api/state").json()["official_alerts"]
    assert alerts[-1]["id"] == "district-galchhi-muglin"


def test_resume_at_the_end_is_refused(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    _start_replay(meshed_nodes)
    assert meshed_nodes["hub"].post("/api/replay/jump", json={"phase": "end"}).status_code == 200
    # The end phase is the replay's last second, so the Hub pauses there by itself at once; a pause
    # sent by the test raced it and was refused whenever the Hub got there first.
    _wait_until(lambda: _event_clock(meshed_nodes, "hub")["state"] == "paused")
    response = meshed_nodes["hub"].post("/api/replay/resume")
    assert response.status_code == 409
    assert "ended" in response.json()["detail"]


def _wait_until_heard_just_now(meshed_nodes: MeshedNodes, node: str) -> None:
    _wait_until(lambda: _heard_from(meshed_nodes, "hub", node)["age_s"] == 0)


# Event seconds at which each gauge has finished its surge.
SURGE_ENDS = {"S0": 8 * 60, "S1": 15 * 60, "S2": 20 * 60, "S3": 80 * 60}


@pytest.mark.parametrize("first_publish_event_seconds", [0, 30, 60])
def test_every_sensors_surge_reaches_the_hub_in_a_replay_from_the_start(
    meshed_nodes: MeshedNodes, first_publish_event_seconds: int
) -> None:
    meshed_nodes.start_hub()
    for track in SURGE_ENDS:
        meshed_nodes.start_sensor(track.lower(), river_km=STATION_KM[track])
        # Only Registered Nodes count toward Flood Risk, and a Surge is read from Flood Risk.
        meshed_nodes[track.lower()].post("/api/registry/signup")
        meshed_nodes["hub"].post("/api/registry/accept", json={"id": track.lower()})
    _start_replay(meshed_nodes)
    # Where a Sensor's publishes fall against the ramp depends on when it joined, so try several.
    meshed_nodes.advance(first_publish_event_seconds / RATE)
    surged: set[str] = set()
    elapsed = first_publish_event_seconds
    # One step is one real publish interval, which is 30 event seconds at x30.
    while elapsed < max(SURGE_ENDS.values()):
        meshed_nodes.advance(REPLAY_PUBLISH_EVERY_SECONDS)
        elapsed += REPLAY_PUBLISH_EVERY_SECONDS * RATE
        for track in SURGE_ENDS:
            _wait_until_heard_just_now(meshed_nodes, track.lower())
        state = meshed_nodes["hub"].get("/api/state").json()
        surged.update(state["flood_risk"]["surged"])
    assert surged == {"s0", "s1", "s2", "s3"}


@pytest.mark.parametrize("rate", [5, 10])
def test_the_collapse_surge_still_reaches_the_hub_at_a_slower_rate(
    meshed_nodes: MeshedNodes, rate: int
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s0", river_km=-12.2)
    meshed_nodes["s0"].post("/api/registry/signup")
    meshed_nodes["hub"].post("/api/registry/accept", json={"id": "s0"})
    meshed_nodes["hub"].post("/api/replay/rate", json={"rate": rate})
    _start_replay(meshed_nodes)
    surged: set[str] = set()
    elapsed = 0
    while elapsed < SURGE_ENDS["S0"]:
        meshed_nodes.advance(REPLAY_PUBLISH_EVERY_SECONDS)
        elapsed += REPLAY_PUBLISH_EVERY_SECONDS * rate
        _wait_until_heard_just_now(meshed_nodes, "s0")
        surged.update(meshed_nodes["hub"].get("/api/state").json()["flood_risk"]["surged"])
    assert surged == {"s0"}
