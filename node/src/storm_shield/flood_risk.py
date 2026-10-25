import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from storm_shield.community_reading import CommunityReading
from storm_shield.region import FlashFlood, FloodWarning, StormSurge

# The unit each kind this Rule set reads is sent in. Any other kind is ignored; a known kind in
# another unit is ignored too, since reading its number as if it were in this unit would be wrong.
WATER_LEVEL, WATER_UNIT = "water_level", "m"
RAIN_RATE, RAIN_UNIT = "rain_rate", "mm/h"
SOIL_MOISTURE, SOIL_UNIT = "soil_moisture", "%"
AIR_PRESSURE, AIR_PRESSURE_UNIT = "air_pressure", "hPa"

logger = logging.getLogger(__name__)
# So a Node that keeps sending the wrong unit fills the log once, not every few seconds.
_logged_unit_mismatches: set[tuple[str, str, str]] = set()

NodeLevel = Literal["elevated", "high"]
FloodRiskLevel = Literal["low", "elevated", "high"]
ReasonCode = Literal[
    "water_surge", "water_high", "water_rising", "rain_heavy", "pressure_falling", "raining"
]


class Reason(BaseModel):
    code: ReasonCode
    nodes: int
    value: float
    seconds: int | None = None  # only a Surge says how long the rise took


class StormSignal(BaseModel):
    on: bool
    nodes: int
    pressure_hpa: float | None


class FloodRisk(BaseModel):
    level: FloodRiskLevel | None
    reasons: list[Reason]
    storm_signal: StormSignal
    nodes: dict[str, NodeLevel | None]
    surged: list[str]  # ids of the Nodes whose water is surging now


@dataclass
class _NodeView:
    """What one Node's recent readings say, before comparing it with the other Nodes.

    A kind the Node never sent is None (or no gain), so it takes no part in any rule.
    """

    rules: FloodWarning
    water_cm: float | None
    water_gain_cm: float
    # Between the first and newest water level in the history, on the sender's clock.
    water_gain_seconds: int
    surge_rise_cm: float
    surge_seconds: int
    rain_mmh: float | None
    soil_gain_points: float
    pressure_hpa: float | None

    @classmethod
    def of(cls, node: str, readings: list[CommunityReading], rules: FloodWarning) -> "_NodeView":
        water = _series(node, readings, WATER_LEVEL, WATER_UNIT)
        rain = _series(node, readings, RAIN_RATE, RAIN_UNIT)
        soil = _series(node, readings, SOIL_MOISTURE, SOIL_UNIT)
        pressure = _series(node, readings, AIR_PRESSURE, AIR_PRESSURE_UNIT)
        newest_water_t, newest_water = water[-1] if water else (0, 0.0)
        # Only a flash flood has a Surge. Its window counts in the sender's own timestamps, so a
        # slow rise cannot pass for one just because its readings arrived together.
        surge_window_s = (
            rules.water_levels.surge_window_s if isinstance(rules.water_levels, FlashFlood) else 0
        )
        in_surge_window = [w for w in water if newest_water_t - w[0] <= surge_window_s]
        lowest_t, lowest = min(in_surge_window, key=lambda w: w[1], default=(0, 0.0))
        # With a single reading there is no trend, so nothing is rising.
        return cls(
            rules=rules,
            water_cm=newest_water * 100 if water else None,
            water_gain_cm=(newest_water - water[0][1]) * 100 if water else 0.0,
            water_gain_seconds=newest_water_t - water[0][0] if water else 0,
            surge_rise_cm=round((newest_water - lowest) * 100, 1) if water else 0.0,
            surge_seconds=newest_water_t - lowest_t if water else 0,
            rain_mmh=rain[-1][1] if rain else None,
            soil_gain_points=soil[-1][1] - soil[0][1] if soil else 0.0,
            pressure_hpa=pressure[-1][1] if pressure else None,
        )

    @property
    def surging(self) -> bool:
        levels = self.rules.water_levels
        return isinstance(levels, FlashFlood) and self.surge_rise_cm >= levels.surge_rise.cm

    @property
    def passing_warning_height(self) -> bool:
        levels = self.rules.water_levels
        return (
            isinstance(levels, StormSurge)
            and self.water_rising
            and _reaches(self.water_cm, levels.warning_height.cm)
        )

    @property
    def water_rising(self) -> bool:
        return self.water_gain_cm >= self.rules.water_levels.rising.cm

    @property
    def soil_rising(self) -> bool:
        return self.soil_gain_points >= self.rules.soil_rising_points

    @property
    def level(self) -> NodeLevel | None:
        levels = self.rules.water_levels
        if (
            self.surging
            or _reaches(self.water_cm, levels.high_level.cm)
            or (_reaches(self.rain_mmh, self.rules.rain_high.mm_per_hour) and self.water_rising)
        ):
            return "high"
        if _reaches(self.water_cm, levels.elevated_level.cm) or _reaches(
            self.rain_mmh, self.rules.rain_elevated.mm_per_hour
        ):
            return "elevated"
        return "elevated" if self.water_rising else None


def _reaches(value: float | None, limit: float) -> bool:
    return value is not None and value >= limit


def _series(
    node: str, readings: list[CommunityReading], kind: str, unit: str
) -> list[tuple[int, float]]:
    """Each reading's (sender timestamp, value) for `kind`, oldest first, in the unit this Rule set reads."""
    series = []
    for reading in readings:
        for measured_kind, value, measured_unit in reading.m:
            if measured_kind != kind:
                continue
            if measured_unit == unit:
                series.append((reading.t, value))
            elif (node, kind, measured_unit) not in _logged_unit_mismatches:
                _logged_unit_mismatches.add((node, kind, measured_unit))
                logger.warning(
                    "ignoring %s from Node %s: sent in %s, the flood-warning rules read %s",
                    kind,
                    node,
                    measured_unit,
                    unit,
                )
    return series


def flood_risk(
    recent: dict[str, list[CommunityReading]],
    registered_ids: Collection[str],
    rules: FloodWarning,
) -> FloodRisk:
    """Flood Risk for everything this Node can see, from each counted Node's recent readings."""
    views = {
        node: _NodeView.of(node, readings, rules)
        for node, readings in recent.items()
        if _counts(node, registered_ids)
    }
    node_levels = {node: view.level for node, view in views.items()}

    low_pressure = [
        view
        for view in views.values()
        if view.pressure_hpa is not None and view.pressure_hpa < rules.storm_pressure.hpa
    ]
    storm_on = bool(low_pressure) and len(low_pressure) * 2 >= len(views)
    storm = low_pressure if storm_on else []
    soil_rising = [view for view in views.values() if view.soil_rising]
    # One odd sensor cannot make it rain, but a lone Node is believed on its own.
    needed = min(2, len(views))
    raining = bool(views) and len(soil_rising) >= needed

    surged = {node: view for node, view in views.items() if view.surging}

    reasons = [
        reason
        for reason in [
            _surge_reason(list(surged.values())),
            _reason(
                "water_high",
                max,
                [
                    v.water_cm
                    for v in views.values()
                    if v.water_cm is not None and v.water_cm >= rules.water_levels.elevated_level.cm
                ],
            ),
            _reason(
                "water_rising", max, [v.water_gain_cm for v in views.values() if v.water_rising]
            ),
            _reason(
                "rain_heavy",
                max,
                [
                    v.rain_mmh
                    for v in views.values()
                    if v.rain_mmh is not None and v.rain_mmh >= rules.rain_elevated.mm_per_hour
                ],
            ),
            _reason(
                "pressure_falling",
                min,
                [v.pressure_hpa for v in storm if v.pressure_hpa is not None],
            ),
            _reason("raining", max, [v.soil_gain_points for v in soil_rising] if raining else []),
        ]
        if reason
    ]

    own_levels = set(node_levels.values())
    headline: FloodRiskLevel | None = None
    if "high" in own_levels:
        headline = "high"
    elif "elevated" in own_levels:
        headline = "elevated"
    elif raining or storm_on:
        headline = "low"
    return FloodRisk(
        level=headline,
        reasons=reasons,
        storm_signal=StormSignal(
            on=storm_on,
            nodes=len(storm),
            pressure_hpa=min(
                (v.pressure_hpa for v in storm if v.pressure_hpa is not None), default=None
            ),
        ),
        nodes=node_levels,
        surged=sorted(surged),
    )


@dataclass(frozen=True)
class WarningTrigger:
    """What a Registered Node's readings say when its Hazard's Community Warning fires."""

    river_km: float | None
    level_m: float | None
    rise_m: float
    rise_seconds: int  # on the sender's clock


def warning_triggers(
    recent: dict[str, list[CommunityReading]],
    registered_ids: Collection[str],
    rules: FloodWarning,
) -> dict[str, WarningTrigger]:
    """Each counted Node whose water fires the Hazard's Community Warning now, by id.

    A flash flood fires on a Surge; a storm surge on the level passing `warning_height` while it
    has risen `rising` across the history.
    """
    triggers = {}
    for node, readings in recent.items():
        if not _counts(node, registered_ids):
            continue
        view = _NodeView.of(node, readings, rules)
        if view.surging or view.passing_warning_height:
            triggers[node] = WarningTrigger(
                river_km=readings[-1].river_km,
                level_m=None if view.water_cm is None else view.water_cm / 100,
                rise_m=view.water_gain_cm / 100,
                rise_seconds=view.water_gain_seconds,
            )
    return triggers


def _counts(node: str, registered_ids: Collection[str]) -> bool:
    # The one place that decides whether a Node's readings count. Silent Nodes never reach it:
    # the reading store leaves them out of `recent` (0021).
    return node in registered_ids


def _surge_reason(surging: list[_NodeView]) -> Reason | None:
    if not surging:
        return None
    biggest = max(surging, key=lambda view: view.surge_rise_cm)
    return Reason(
        code="water_surge",
        nodes=len(surging),
        value=biggest.surge_rise_cm,
        seconds=biggest.surge_seconds,
    )


def _reason(
    code: ReasonCode, most_telling: Callable[[list[float]], float], values: list[float]
) -> Reason | None:
    return (
        Reason(code=code, nodes=len(values), value=round(most_telling(values), 1))
        if values
        else None
    )
