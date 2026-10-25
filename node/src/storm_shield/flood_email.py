import logging
import smtplib
import threading
from datetime import UTC, datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from storm_shield.community_warning import CommunityWarning
from storm_shield.region import Length, Region
from storm_shield.settings import Settings

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_SSL_PORT = 465
# A hung server must not leave a sender thread behind for the rest of the demo.
SMTP_TIMEOUT_SECONDS = 15
NEPAL_TIME = timezone(timedelta(hours=5, minutes=45))

SUBJECT = "ALERT OF FLOOD INCOMING!"
# Loud on purpose: a Replay runs the same surge code, and the team must never mistake it
# for the river.
REHEARSAL_SUBJECT = f"*** REHEARSAL, NOT A REAL FLOOD *** {SUBJECT}"


class FloodEmail:
    """The Hub's email to the team when it issues a new Community Warning.

    Optional and best effort: it needs internet, so it sits beside the Mesh warning and never
    stands in for it. A failed send is logged and nothing else happens.
    """

    def __init__(
        self,
        sender: str,
        app_password: str,
        recipients: list[str],
        dashboard_url: str,
        region: Region,
    ) -> None:
        self._region = region
        self._sender = sender
        self._app_password = app_password
        self._recipients = recipients
        self._dashboard_url = dashboard_url

    @classmethod
    def from_settings(cls, settings: Settings, region: Region) -> "FloodEmail | None":
        """None unless this is the Hub and all three email settings are set."""
        recipients = [
            address.strip() for address in settings.alert_email_to.split(",") if address.strip()
        ]
        if (
            settings.role != "hub"
            or not settings.alert_email_from
            or not settings.alert_email_app_password
            or not recipients
        ):
            return None
        return cls(
            settings.alert_email_from,
            settings.alert_email_app_password,
            recipients,
            settings.dashboard_url,
            region,
        )

    def send_for(self, warning: CommunityWarning, rehearsal: bool) -> None:
        """Send in the background so a slow SMTP server cannot delay the warning."""
        threading.Thread(target=self._deliver, args=(warning, rehearsal), daemon=True).start()

    def _deliver(self, warning: CommunityWarning, rehearsal: bool) -> None:
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_SSL_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.login(self._sender, self._app_password)
                smtp.send_message(self._message(warning, rehearsal))
        except (OSError, smtplib.SMTPException) as error:
            # Only the type: an SMTP error's text can echo the login.
            logger.warning(
                "could not email the flood alert for %s: %s", warning.origin, type(error).__name__
            )

    def _message(self, warning: CommunityWarning, rehearsal: bool) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = REHEARSAL_SUBJECT if rehearsal else SUBJECT
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message.set_content(
            f"{message['Subject']}\n\n"
            + (
                self._storm_surge_lines(warning)
                if warning.hazard == "storm_surge"
                else self._flash_flood_lines(warning)
            )
        )
        return message

    def _flash_flood_lines(self, warning: CommunityWarning) -> str:
        surge_time = datetime.fromtimestamp(warning.surge_t, UTC).astimezone(NEPAL_TIME)
        return (
            f"Node {warning.origin} reported a sudden rise in the river at "
            f"km {warning.origin_km:g}, at {surge_time:%H:%M} Nepal time. "
            "A flood may be coming down the river.\n\n"
            "This is a Storm Shield Community Warning, not an official alert. "
            f"Open the Storm Shield dashboard ({self._dashboard_url}) to see the arrival estimate "
            "and the nearest open Shelter, and follow your official sources (DHM and your district) for instructions."
        )

    def _storm_surge_lines(self, warning: CommunityWarning) -> str:
        at = datetime.fromtimestamp(warning.surge_t, ZoneInfo(self._region.time_zone))
        unit = self._region.display_units.water_level
        cm_per_unit = Length(value=1, unit=unit).cm

        def in_unit(metres: float) -> str:
            return f"{metres * 100 / cm_per_unit:.1f} {unit}"

        level = f" at {in_unit(warning.level_m)}" if warning.level_m is not None else ""
        rise = (
            f"rising {in_unit(warning.rise_m_per_h)} an hour"
            if warning.rise_m_per_h is not None
            else "rising"
        )
        sources = " and ".join(source.name for source in self._region.official_alert_sources)
        return (
            f"Node {warning.origin} reported the water{level}, {rise}, "
            f"at {at:%H:%M %Z}. A storm surge may be coming ashore.\n\n"
            "This is a Storm Shield Community Warning, not an official alert. "
            f"Open the Storm Shield dashboard ({self._dashboard_url}) to see when the water may "
            f"reach your ground and the nearest open Shelter, and follow your official sources "
            f"({sources}) for instructions."
        )
