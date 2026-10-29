import time
from collections.abc import Callable

import pytest
import RNS
from fixture_pack import nepal_event
from meshed_nodes import MeshedNodes

from storm_shield.official_alert import HEADLINE_MAX_LENGTH, OfficialAlert
from storm_shield.region import ALERT_TAG_MAX_LENGTH
from storm_shield.reticulum_mesh import SIGNATURE_LENGTH

pytestmark = pytest.mark.usefixtures("nepal_region")

# 08:30 NPT on 26 Aug 2026, the first moment of the replay timeline; 1 s of real time is 30 s.
REPLAY_START = 1787712300
RATE = 30
# Real seconds after the start until the Event clock reads 09:05 and 09:15.
TO_DHM_NOTICE = 35 * 60 / RATE
TO_DHM_SMS = 45 * 60 / RATE

EVERY_NODE = ("hub", "s2", "porch")


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _alerts(meshed_nodes: MeshedNodes, name: str) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = meshed_nodes[name].get("/api/state").json()["official_alerts"]
    return alerts


def _alert_ids(meshed_nodes: MeshedNodes, name: str) -> list[object]:
    return [alert["id"] for alert in _alerts(meshed_nodes, name)]


def _wait_for_alert_ids(meshed_nodes: MeshedNodes, name: str, ids: list[str]) -> None:
    _wait_until(lambda: _alert_ids(meshed_nodes, name) == ids)


def _start_valley(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("s2", river_km=14.6)
    meshed_nodes.start("porch")
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200


def test_a_replayed_alert_reaches_every_node_at_its_event_time_and_not_before(
    meshed_nodes: MeshedNodes,
) -> None:
    _start_valley(meshed_nodes)
    meshed_nodes.advance(TO_DHM_SMS - 0.5)
    for name in EVERY_NODE:
        _wait_for_alert_ids(meshed_nodes, name, ["dhm-notice"])
    time.sleep(0.1)
    assert all(_alert_ids(meshed_nodes, name) == ["dhm-notice"] for name in EVERY_NODE)

    meshed_nodes.advance(0.5)
    for name in EVERY_NODE:
        _wait_for_alert_ids(meshed_nodes, name, ["dhm-notice", "dhm-sms"])
        sms = _alerts(meshed_nodes, name)[1]
        assert sms["mode"] == "replay"
        assert sms["source"] == "dhm"
        assert sms["issued"] == "2026-08-26T09:15:00+05:45"
        assert sms["applies_to"] == ["flood_prone_area"]


def test_no_official_alert_shows_before_the_replay_starts(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    meshed_nodes.advance(TO_DHM_SMS * 2)
    time.sleep(0.1)
    assert _alerts(meshed_nodes, "hub") == []
    assert _alerts(meshed_nodes, "porch") == []


def test_a_reset_hides_the_alerts_the_replay_has_not_reached_again(
    meshed_nodes: MeshedNodes,
) -> None:
    _start_valley(meshed_nodes)
    meshed_nodes.advance(TO_DHM_NOTICE + 1)
    _wait_for_alert_ids(meshed_nodes, "porch", ["dhm-notice"])
    assert meshed_nodes["hub"].post("/api/replay/reset").status_code == 200
    for name in EVERY_NODE:
        assert _alerts(meshed_nodes, name) == []


def test_a_node_that_joins_late_gets_the_alerts_already_sent(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(replay_repeat_seconds=0.02)
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200
    meshed_nodes.advance(TO_DHM_NOTICE + 1)
    _wait_for_alert_ids(meshed_nodes, "hub", ["dhm-notice"])
    meshed_nodes.start_sensor("late", river_km=54.0)
    _wait_for_alert_ids(meshed_nodes, "late", ["dhm-notice"])


def test_an_official_alert_not_from_the_hub_is_ignored(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    meshed_nodes.announce_replay("playing", REPLAY_START + 3 * 3600)
    forged = nepal_event().official_alerts_due(REPLAY_START + 3 * 3600)[0]
    meshed_nodes.announce_official_alert(forged, sender="intruder")
    assert _alerts(meshed_nodes, "porch") == []
    meshed_nodes.announce_official_alert(forged)
    assert _alert_ids(meshed_nodes, "porch") == [forged.id]


def test_the_replayed_alerts_keep_their_real_times_and_source_links() -> None:
    alerts = nepal_event().official_alerts_due(REPLAY_START + 3 * 3600)
    assert [(alert.issued[11:16], alert.source) for alert in alerts] == [
        ("09:05", "dhm"),
        ("09:15", "dhm"),
        ("10:28", "district"),
    ]
    assert all(alert.url.startswith("https://") for alert in alerts)


def test_the_longest_alert_the_region_allows_fits_one_reticulum_packet() -> None:
    alert = nepal_event().official_alerts_due(REPLAY_START + 3 * 3600)[0]
    longest = alert.model_copy(
        update={"source": "x" * ALERT_TAG_MAX_LENGTH, "headline": "h" * HEADLINE_MAX_LENGTH}
    )
    assert SIGNATURE_LENGTH + len(longest.model_dump_json().encode()) <= RNS.Packet.PLAIN_MDU


def test_every_replayed_alert_fits_one_reticulum_packet() -> None:
    alerts: list[OfficialAlert] = nepal_event().official_alerts_due(REPLAY_START + 3 * 3600)
    for alert in alerts:
        signed_bytes = SIGNATURE_LENGTH + len(alert.model_dump_json().encode())
        assert signed_bytes <= RNS.Packet.PLAIN_MDU, alert.id
