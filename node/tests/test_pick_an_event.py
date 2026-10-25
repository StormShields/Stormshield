import json
from pathlib import Path

import pytest
from meshed_nodes import MeshedNodes

from storm_shield import region
from storm_shield.region import events_dir, region_path


@pytest.fixture(autouse=True)
def two_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Nepal Event plus a made-up one with a different phase list, in a Region of their own."""
    nepal_dir = tmp_path / "nepal"
    events = nepal_dir / "events"
    events.mkdir(parents=True)
    (nepal_dir / "region.json").write_text(region_path("nepal").read_text())
    nepal = json.loads((events_dir("nepal") / "bhote-koshi-2026.json").read_text())
    (events / "bhote-koshi-2026.json").write_text(json.dumps(nepal))
    made_up = {
        **nepal,
        "id": "made-up-flood",
        "label": "A made-up flood",
        "phases": [{"id": "only", "at": "09:00:00", "label": "The only phase"}],
    }
    (events / "made-up-flood.json").write_text(json.dumps(made_up))
    monkeypatch.setattr(region, "REGIONS_DIR", tmp_path)


def test_the_hub_lists_the_events_it_holds(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    listed = meshed_nodes["hub"].get("/api/replay/events").json()["events"]
    assert [event["id"] for event in listed] == ["bhote-koshi-2026", "made-up-flood"]
    assert listed[1]["label"] == "A made-up flood"


def test_a_picked_event_plays_on_every_node(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("porch")
    started = meshed_nodes["hub"].post("/api/replay/start", json={"event": "made-up-flood"})
    assert started.status_code == 200
    for name in ("hub", "porch"):
        clock = meshed_nodes[name].get("/api/replay").json()
        assert (clock["event"], clock["state"]) == ("made-up-flood", "playing")


def test_the_controls_follow_the_event_on_the_clock(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    hub = meshed_nodes["hub"]
    hub.post("/api/replay/start", json={"event": "made-up-flood"})
    assert [p["id"] for p in hub.get("/api/replay/phases").json()["phases"]] == ["only"]
    assert hub.post("/api/replay/jump", json={"phase": "only"}).json()["event"] == "made-up-flood"
    assert hub.post("/api/replay/reset").json()["event"] == "made-up-flood"
    assert hub.post("/api/replay/start").json()["event"] == "made-up-flood"


def test_jump_and_reset_act_on_the_picked_event_while_the_clock_is_stopped(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    hub = meshed_nodes["hub"]
    jumped = hub.post("/api/replay/jump", json={"phase": "only", "event": "made-up-flood"})
    assert jumped.json()["event"] == "made-up-flood"
    hub.post("/api/replay/reset", json={"event": "bhote-koshi-2026"})
    assert hub.get("/api/replay").json()["event"] == "bhote-koshi-2026"


def test_phases_can_be_asked_for_before_the_event_plays(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    hub = meshed_nodes["hub"]
    answer = hub.get("/api/replay/phases", params={"event": "made-up-flood"})
    assert [p["id"] for p in answer.json()["phases"]] == ["only"]
    assert hub.get("/api/replay/phases", params={"event": "nope"}).status_code == 404


def test_an_unknown_event_is_refused(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    hub = meshed_nodes["hub"]
    assert hub.post("/api/replay/start", json={"event": "nope"}).status_code == 422
    assert hub.get("/api/replay").json()["state"] == "stopped"
