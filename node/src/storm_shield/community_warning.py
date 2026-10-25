import logging
import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from storm_shield.flood_risk import WarningTrigger
from storm_shield.region import Hazard

if TYPE_CHECKING:
    from storm_shield.replay import ReplayClockMessage

WarningReason = Literal[
    "water_surge", "water_high", "water_rising", "rain_heavy", "pressure_falling"
]


logger = logging.getLogger(__name__)

# Just above the fastest reconstructed reach (190 km/h); a faster "measurement" is two unrelated
# Surges or a bad clock, not a wave.
MAX_MEASURED_SPEED_KMH = 300.0
SECONDS_PER_HOUR = 3600


class MeasuredSpeed(BaseModel):
    """The wave's speed between the warning's origin and `node`, the next Node downstream to surge."""

    node: str
    km: float
    surge_t: int
    speed_kmh: float


class CommunityWarning(BaseModel):
    """A Community Warning in the mesh format of docs/specs/wire-formats.md; only the Hub sends one.

    There is no text field on purpose: the "not official" label and the pointer to official
    sources are fixed dashboard text that no message can drop or reword.
    """

    v: Literal[2] = 2
    kind: Literal["warning"] = "warning"
    # Counts up on the Hub; a Node tells a repeat from a new warning by it.
    id: int
    t: int
    # Picks the trigger and the title the dashboard shows.
    hazard: Hazard
    nodes: list[str]
    reasons: list[WarningReason]
    origin: str
    # The origin's River km on a flash flood; a coast has no river.
    origin_km: float | None
    # Event time the trigger fired; named when a Surge was the only trigger.
    surge_t: int
    # A storm surge's level and rate of rise at the origin, from which each Viewer works out its
    # own Water ETA. The rate is per hour of Event time.
    level_m: float | None = None
    rise_m_per_h: float | None = None
    # Set by a repeat of the same warning (same id) once a second Node has surged downstream.
    measured: MeasuredSpeed | None = None


class HubWarnings:
    """The Hub's side of Community Warnings: decides when one is due and remembers what it sent."""

    def __init__(self, first_id: int) -> None:
        # The Reticulum receive thread issues while request threads read the log.
        self._lock = threading.Lock()
        self._next_id = first_id
        self._warned: set[str] = set()
        self._unplaced: set[str] = set()
        self._sent: list[CommunityWarning] = []

    def issue_for_new_triggers(
        self,
        hazard: Hazard,
        triggers: Mapping[str, WarningTrigger],
        surge_t: int,
        now: int,
        event_seconds_per_second: float,
    ) -> list[CommunityWarning]:
        """One warning for each Node in `triggers` not already warned about.

        A Node is forgotten once its trigger stops holding, so a second one warns again.

        On a flash flood, a Node with no River km cannot be placed on the river, so it gets no
        warning, and a log line once. A Node that surges below, and after, a warning with no
        measurement yet does not get a warning of its own: that warning is returned again (same
        id) with the measured speed. A storm surge carries the origin's level and rate of rise
        instead, the rate turned from the sender's clock into Event time by
        `event_seconds_per_second`.
        """
        with self._lock:
            self._warned &= triggers.keys()
            self._unplaced &= triggers.keys()
            issued: list[CommunityWarning] = []
            for node, trigger in sorted(triggers.items()):
                if node in self._warned:
                    continue
                if hazard == "storm_surge":
                    warning = self._new_warning(hazard, node, None, surge_t, now).model_copy(
                        update=_level_and_rise(trigger, event_seconds_per_second)
                    )
                elif trigger.river_km is None:
                    if node not in self._unplaced:
                        logger.warning("Node %s is surging but has no NODE_RIVER_KM", node)
                        self._unplaced.add(node)
                    continue
                elif found := self._measure_with(node, trigger.river_km, surge_t):
                    index, update = found
                    self._sent[index] = update
                    issued.append(update)
                    self._warned.add(node)
                    continue
                else:
                    warning = self._new_warning(hazard, node, trigger.river_km, surge_t, now)
                issued.append(warning)
                self._sent.append(warning)
                self._next_id += 1
                self._warned.add(node)
            return issued

    def _new_warning(
        self, hazard: Hazard, node: str, river_km: float | None, surge_t: int, now: int
    ) -> CommunityWarning:
        return CommunityWarning(
            id=self._next_id,
            t=now,
            hazard=hazard,
            nodes=[node],
            reasons=["water_surge"] if hazard == "flash_flood" else ["water_high", "water_rising"],
            origin=node,
            origin_km=river_km,
            surge_t=surge_t,
        )

    def _measure_with(
        self, node: str, river_km: float, surge_t: int
    ) -> tuple[int, CommunityWarning] | None:
        """The newest unmeasured warning this Node's Surge measures, with that warning updated.

        Only one measurement is made per warning; the speed must be a plausible wave speed.
        """
        for index in range(len(self._sent) - 1, -1, -1):
            warning = self._sent[index]
            if warning.measured is not None or warning.origin_km is None:
                continue
            hours = (surge_t - warning.surge_t) / SECONDS_PER_HOUR
            distance_km = river_km - warning.origin_km
            if hours <= 0 or distance_km <= 0:
                continue
            speed_kmh = distance_km / hours
            if speed_kmh > MAX_MEASURED_SPEED_KMH:
                continue
            measured = MeasuredSpeed(
                node=node, km=river_km, surge_t=surge_t, speed_kmh=round(speed_kmh, 1)
            )
            return index, warning.model_copy(update={"measured": measured})
        return None

    def sent(self) -> list[CommunityWarning]:
        """Every warning sent since this Hub started, newest first."""
        with self._lock:
            return self._sent[::-1]


def _level_and_rise(
    trigger: WarningTrigger, event_seconds_per_second: float
) -> dict[str, float | None]:
    event_hours = trigger.rise_seconds * event_seconds_per_second / SECONDS_PER_HOUR
    return {
        "level_m": None if trigger.level_m is None else round(trigger.level_m, 3),
        "rise_m_per_h": round(trigger.rise_m / event_hours, 3) if event_hours > 0 else None,
    }


def _without_unreached_measurement(warning: CommunityWarning, event_t: int) -> CommunityWarning:
    if warning.measured is None or warning.measured.surge_t <= event_t:
        return warning
    return warning.model_copy(update={"measured": None})


def _id(warning: CommunityWarning) -> int:
    return warning.id


class HeardCommunityWarnings:
    """Every Community Warning this Node has heard from the Hub, by id."""

    def __init__(self) -> None:
        # The Reticulum receive thread writes while request threads read.
        self._lock = threading.Lock()
        self._by_id: dict[int, CommunityWarning] = {}

    def hear(self, warning: CommunityWarning) -> None:
        with self._lock:
            known = self._by_id.get(warning.id)
            # An older copy of the same warning, reordered on the Mesh, must not undo the update.
            if known and known.measured and not warning.measured:
                return
            self._by_id[warning.id] = warning

    def shown_at(self, event: "ReplayClockMessage") -> list[CommunityWarning]:
        """The warnings to show, oldest first.

        While a replay runs, a warning shows only once the Event clock has reached its Surge, so a
        reset or a jump back hides it without the Hub taking it back; with no replay all show.
        """
        with self._lock:
            warnings = list(self._by_id.values())
        if event.state != "stopped":
            warnings = [warning for warning in warnings if warning.surge_t <= event.event_t]
            warnings = [
                _without_unreached_measurement(warning, event.event_t) for warning in warnings
            ]
        # A replay run again warns about the same Node under a new id; only the newest shows.
        newest_per_origin = {warning.origin: warning for warning in sorted(warnings, key=_id)}
        return sorted(newest_per_origin.values(), key=_id)
