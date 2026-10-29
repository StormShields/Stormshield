import logging
import smtplib
import time
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest
from fixture_pack import build_nepal_pack
from meshed_nodes import MeshedNodes

from storm_shield.community_warning import CommunityWarning
from storm_shield.flood_email import FloodEmail
from storm_shield.region import load_region, region_path
from storm_shield.settings import Settings

pytestmark = pytest.mark.usefixtures("nepal_region")

LOGIN_TEXT = "app-password-1234"
EMAIL_SETTINGS: dict[str, Any] = {
    "alert_email_from": "team@example.org",
    "alert_email_app_password": LOGIN_TEXT,
    "alert_email_to": "one@example.org, two@example.org",
}
S0_RIVER_KM = -12.2


class FakeSmtp:
    """Stands in for Gmail's SMTP server; `fail_with` makes every connection fail."""

    sent: ClassVar[list[EmailMessage]] = []
    logins: ClassVar[list[tuple[str, str]]] = []
    attempts = 0
    fail_with: Exception | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        FakeSmtp.attempts += 1
        if FakeSmtp.fail_with:
            raise FakeSmtp.fail_with

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        FakeSmtp.logins.append((user, password))

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.sent, FakeSmtp.logins, FakeSmtp.attempts, FakeSmtp.fail_with = [], [], 0, None
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 3
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.01)


def _register(meshed_nodes: MeshedNodes, node: str) -> None:
    meshed_nodes.announce_sign_up(node, node)
    assert meshed_nodes["hub"].post("/api/registry/accept", json={"id": node}).status_code == 200


def _surge(meshed_nodes: MeshedNodes, node: str, river_km: float = S0_RIVER_KM) -> None:
    meshed_nodes.hear_from(node, water_cm=20, river_km=river_km)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from(node, water_cm=340, river_km=river_km)


def _warning_log(meshed_nodes: MeshedNodes) -> list[dict[str, Any]]:
    return meshed_nodes["hub"].get("/api/warnings").json()["warnings"]  # type: ignore[no-any-return]


def test_a_new_warning_emails_the_team_with_the_node_the_river_km_and_the_time(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub(**EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")

    _surge(meshed_nodes, "s0")

    _wait_until(lambda: len(FakeSmtp.sent) == 1)
    message = FakeSmtp.sent[0]
    assert message["Subject"] == "ALERT OF FLOOD INCOMING!"
    assert message["To"] == "one@example.org, two@example.org"
    assert FakeSmtp.logins == [("team@example.org", LOGIN_TEXT)]
    body = message.get_content()
    assert "s0" in body
    assert "km -12.2" in body
    assert "Nepal time" in body
    assert "not an official alert" in body
    assert "http://10.88.0.1:" in body


def test_the_email_does_not_order_an_evacuation(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(**EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")
    _surge(meshed_nodes, "s0")
    _wait_until(lambda: len(FakeSmtp.sent) == 1)

    body = FakeSmtp.sent[0].get_content().lower()

    assert "evacuate" not in body
    assert "you must" not in body


def test_the_same_surge_holding_does_not_email_again(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(**EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")
    _surge(meshed_nodes, "s0")
    _wait_until(lambda: len(FakeSmtp.sent) == 1)

    meshed_nodes.advance(10)
    meshed_nodes.hear_from("s0", water_cm=350, river_km=S0_RIVER_KM)
    meshed_nodes.advance(10)
    meshed_nodes.hear_from("s0", water_cm=360, river_km=S0_RIVER_KM)

    time.sleep(0.2)
    assert FakeSmtp.attempts == 1


def test_a_measured_speed_update_does_not_email_again(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(**EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")
    _register(meshed_nodes, "s1")
    _surge(meshed_nodes, "s0", river_km=0.0)
    _wait_until(lambda: len(FakeSmtp.sent) == 1)

    meshed_nodes.advance(12 * 60 - 8)
    _surge(meshed_nodes, "s1", river_km=15.6)

    assert _warning_log(meshed_nodes)[0]["measured"] is not None
    time.sleep(0.2)
    assert FakeSmtp.attempts == 1


@pytest.mark.parametrize("blank", list(EMAIL_SETTINGS))
def test_no_email_unless_all_three_settings_are_set(meshed_nodes: MeshedNodes, blank: str) -> None:
    meshed_nodes.start_hub(**{**EMAIL_SETTINGS, blank: ""})
    _register(meshed_nodes, "s0")

    _surge(meshed_nodes, "s0")

    assert len(_warning_log(meshed_nodes)) == 1
    time.sleep(0.2)
    assert FakeSmtp.attempts == 0


def test_a_sensor_with_the_settings_sends_nothing() -> None:
    sensor = Settings(role="sensor", **EMAIL_SETTINGS)

    assert FloodEmail.from_settings(sensor, load_region(region_path("nepal"))) is None


def test_a_failing_send_still_issues_the_warning_and_never_logs_the_password(
    meshed_nodes: MeshedNodes, caplog: pytest.LogCaptureFixture
) -> None:
    FakeSmtp.fail_with = smtplib.SMTPAuthenticationError(535, f"bad login {LOGIN_TEXT}".encode())
    meshed_nodes.start_hub(**EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")

    with caplog.at_level(logging.WARNING):
        _surge(meshed_nodes, "s0")
        _wait_until(lambda: "could not email the flood alert" in caplog.text)

    assert len(_warning_log(meshed_nodes)) == 1
    assert "SMTPAuthenticationError" in caplog.text
    assert LOGIN_TEXT not in caplog.text


def test_a_warning_during_a_replay_has_a_loud_rehearsal_subject(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.start_hub(cache_pack=(tmp_path / "packs", build_nepal_pack()), **EMAIL_SETTINGS)
    _register(meshed_nodes, "s0")
    assert meshed_nodes["hub"].post("/api/replay/start").status_code == 200

    _surge(meshed_nodes, "s0")

    _wait_until(lambda: len(FakeSmtp.sent) == 1)
    assert (
        FakeSmtp.sent[0]["Subject"]
        == "*** REHEARSAL, NOT A REAL FLOOD *** ALERT OF FLOOD INCOMING!"
    )
    assert "REHEARSAL" in FakeSmtp.sent[0].get_content()


def test_a_storm_surge_warning_emails_the_level_and_rise_in_the_regions_units_and_time() -> None:
    hub = Settings(role="hub", **EMAIL_SETTINGS)
    email = FloodEmail.from_settings(hub, load_region(region_path("fort-myers")))
    assert email is not None
    warning = CommunityWarning(
        id=1,
        t=1664380800,
        hazard="storm_surge",
        nodes=["pier"],
        reasons=["water_high", "water_rising"],
        origin="pier",
        origin_km=None,
        # 15:05 EDT on 28 Sep 2022.
        surge_t=1664391900,
        level_m=1.5545,
        rise_m_per_h=0.4267,
    )

    email.send_for(warning, rehearsal=False)

    _wait_until(lambda: len(FakeSmtp.sent) == 1)
    body = FakeSmtp.sent[0].get_content()
    assert "water at 5.1 ft, rising 1.4 ft an hour, at 15:05 EDT" in body
    assert "storm surge" in body
    assert "Nepal" not in body
    assert "not an official alert" in body
