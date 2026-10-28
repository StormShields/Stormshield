import itertools
import json
import math
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple, Self

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from storm_shield.community_reading import Position, Reading
from storm_shield.official_alert import AppliesTo, OfficialAlert
from storm_shield.official_gauge import OfficialGaugeLevel
from storm_shield.region import Hazard, LatLon, Region, RegionError, describe_problems, events_dir
from storm_shield.river_line import METRES_PER_DEGREE_OF_LATITUDE


class ReplayClockMessage(BaseModel):
    """The Hub's Event clock, in the mesh format of docs/specs/wire-formats.md."""

    v: Literal[2] = 2
    kind: Literal["replay"] = "replay"
    # The Event every Node plays; a Node that does not hold this Event ignores the clock.
    event: str
    state: Literal["playing", "paused", "stopped"]
    # Event time (Unix seconds) at the moment of sending; receivers anchor it on their own clock.
    event_t: int
    rate: int


class EventClock:
    """What this Node believes the Event clock reads, anchored on its own clock at receipt."""

    def __init__(self, event_id: str) -> None:
        # The Reticulum receive thread writes while request threads read.
        self._lock = threading.Lock()
        self._heard = ReplayClockMessage(event=event_id, state="stopped", event_t=0, rate=1)
        self._heard_at: datetime | None = None

    def hear(self, message: ReplayClockMessage, received_at: datetime) -> None:
        with self._lock:
            self._heard = message
            self._heard_at = received_at

    def current(self, now: datetime) -> ReplayClockMessage:
        """The clock as of `now`; only a playing clock moves."""
        with self._lock:
            heard, heard_at = self._heard, self._heard_at
        if heard.state != "playing" or heard_at is None:
            return heard
        elapsed = (now - heard_at).total_seconds()
        return heard.model_copy(update={"event_t": heard.event_t + int(elapsed * heard.rate)})


class SensorSpot(NamedTuple):
    """Where a Sensor reads the surface: its true position, River km and ground height."""

    position: Position
    # Set on a river Region, inside the river's reach.
    river_km: float | None
    # Metres above the coast surface's datum, from the pack's terrain; None where it has none.
    ground_m: float | None


class Station(BaseModel):
    """A gauge: its level over the Event, as points joined by straight lines."""

    id: str
    label: str
    # (seconds after the Event starts, level in the surface's unit)
    series: list[tuple[int, float]]

    @field_validator("series")
    @classmethod
    def _in_time_order(cls, series: list[tuple[int, float]]) -> list[tuple[int, float]]:
        _require_increasing([at for at, _ in series], "a station's series")
        return series

    def level_at(self, elapsed: int) -> float:
        return _interpolate(elapsed, [(at, (level,)) for at, level in self.series])[0]


class RiverStation(Station):
    river_km: float


class CoastStation(Station):
    pos: LatLon
    # Its series is another station's curve scaled, not a record, and the Replay says so.
    reconstructed: bool = False


class RiverSurface(BaseModel):
    """The river's stage at stations along it; the level between them follows River km."""

    unit: Literal["m"]
    stations: list[RiverStation]

    @field_validator("stations")
    @classmethod
    def _in_river_order(cls, stations: list[RiverStation]) -> list[RiverStation]:
        _require_increasing([station.river_km for station in stations], "the stations")
        return stations

    def level_at(self, spot: SensorSpot, elapsed: int) -> float | None:
        """The stage at the spot; None outside the stations' span, or off the river, where it is dry."""
        stations = self.stations
        if spot.river_km is None or not (
            stations[0].river_km <= spot.river_km <= stations[-1].river_km
        ):
            return None
        return _interpolate(
            spot.river_km,
            [(station.river_km, (station.level_at(elapsed),)) for station in stations],
        )[0]


class CoastSurface(BaseModel):
    """The water surface's height above the Region's datum, blended between stations by distance."""

    datum: Literal["NAVD88"]
    unit: Literal["m"]
    stations: list[CoastStation]

    @field_validator("stations")
    @classmethod
    def _at_least_one(cls, stations: list[CoastStation]) -> list[CoastStation]:
        if not stations:
            raise ValueError("a coast surface needs at least one station")
        return stations

    def level_at(self, spot: SensorSpot, elapsed: int) -> float | None:
        """The surface's height at the spot, or None where it is below the ground (dry).

        A spot with no known ground height is dry too: sending a level for land the water may
        never reach would be worse than sending none.
        """
        if spot.ground_m is None:
            return None
        weighted, weights = 0.0, 0.0
        for station in self.stations:
            distance = _metres_between(spot.position, station.pos)
            level = station.level_at(elapsed)
            if distance < 1:
                weighted, weights = level, 1.0
                break
            weight = 1 / distance**2
            weighted += weight * level
            weights += weight
        level = weighted / weights
        return level if level > spot.ground_m else None


def _metres_between(position: Position, station: tuple[float, float]) -> float:
    # Flat-earth distance is close enough across one Region.
    metres_per_degree_of_longitude = METRES_PER_DEGREE_OF_LATITUDE * math.cos(
        math.radians(position.latitude)
    )
    return math.hypot(
        (station[0] - position.latitude) * METRES_PER_DEGREE_OF_LATITUDE,
        (station[1] - position.longitude) * metres_per_degree_of_longitude,
    )


class WeatherKeyframe(BaseModel):
    t: int
    rain_mmh: float
    soil_pct: float
    pressure_hpa: float


def _require_increasing(positions: list[float], what: str) -> None:
    if not positions or any(b <= a for a, b in itertools.pairwise(positions)):
        raise ValueError(f"{what} must be a non-empty list in strictly increasing order")


class Phase(BaseModel):
    id: str
    at: str
    label: str


class InternetCue(BaseModel):
    at: str


class ReplayedAlert(BaseModel):
    """One Official Alert as the replay file records it; `source` names the citation."""

    id: str
    at: str
    # The day of `at`, when it is not the Event's: an alert already in force when the Event starts.
    date: str | None = None
    # A tag from the Region's `official_alert_sources`.
    issuer: str
    headline: str
    applies_to: list[AppliesTo]
    source: str


class ReplayedGauge(BaseModel):
    """An Official Gauge's recorded levels, which play on the Event clock in place of its live ones."""

    agency: Literal["NOAA"]
    station: str
    # (seconds after the Event starts, metres in the Region's datum)
    series: list[tuple[int, float]]

    @field_validator("series")
    @classmethod
    def _in_time_order(cls, series: list[tuple[int, float]]) -> list[tuple[int, float]]:
        _require_increasing([at for at, _ in series], "a gauge's series")
        return series

    def level_at(self, elapsed: int) -> float:
        return _interpolate(elapsed, [(at, (level,)) for at, level in self.series])[0]


class Event(BaseModel):
    """One Event file, `events/<id>.json`: its window, phases, Official Alerts, surface and weather.

    Each fact in it names its source, or says it is reconstructed.
    """

    id: str
    label: str
    hazard: Hazard
    date: str
    utc_offset: str
    start: str
    end: str
    start_unix: int
    rate: int
    sources: dict[str, str]
    phases: list[Phase]
    internet_cue: InternetCue
    official_alerts: list[ReplayedAlert]
    official_gauges: list[ReplayedGauge] = []
    surface: RiverSurface | CoastSurface
    weather: list[WeatherKeyframe]

    @field_validator("weather")
    @classmethod
    def _weather_in_time_order(cls, weather: list[WeatherKeyframe]) -> list[WeatherKeyframe]:
        _require_increasing([keyframe.t for keyframe in weather], "the weather")
        return weather

    @model_validator(mode="after")
    def _surface_fits_the_hazard(self) -> Self:
        coast = isinstance(self.surface, CoastSurface)
        if coast != (self.hazard == "storm_surge"):
            wanted = "coast" if self.hazard == "storm_surge" else "river"
            raise ValueError(f"a {self.hazard} Event needs a {wanted} surface")
        return self

    def event_t_at(self, clock_time: str) -> int:
        """The Event clock's Unix seconds when the replay reads `clock_time`."""
        return self.start_unix + self._seconds_after_start(clock_time)

    @property
    def end_unix(self) -> int:
        """The Event clock's Unix seconds at the end of the replay, where the Hub stops it."""
        return self.event_t_at(self.end)

    def require_fits(self, region: Region) -> None:
        """Raise RegionError if the Region's water cannot have this Hazard, or an alert is credited
        to a source the Region does not list."""
        if self.hazard != region.hazard:
            raise RegionError(
                f"Event {self.id} is a {self.hazard}, but the {region.name} Region's water makes "
                f"a {region.hazard}"
            )
        for alert in self.official_alerts:
            if not region.has_alert_source(alert.issuer):
                raise RegionError(
                    f"Event {self.id}: alert {alert.id} is from {alert.issuer!r}, which is not "
                    f"one of the {region.name} Region's official_alert_sources"
                )

    def official_alerts_due(self, event_t: int) -> list[OfficialAlert]:
        """The Official Alerts the Event clock has reached, in the mesh format."""
        issued = {
            alert.id: f"{alert.date or self.date}T{alert.at}{self.utc_offset}"
            for alert in self.official_alerts
        }
        return [
            OfficialAlert(
                id=alert.id,
                source=alert.issuer,
                mode="replay",
                issued=issued[alert.id],
                headline=alert.headline,
                applies_to=alert.applies_to,
                url=self.sources[alert.source],
            )
            for alert in self.official_alerts
            if int(datetime.fromisoformat(issued[alert.id]).timestamp()) <= event_t
        ]

    def reconstructed_station_labels(self) -> list[str]:
        """The stations whose series is another station's curve scaled, not a record."""
        return [
            station.label
            for station in self.surface.stations
            if isinstance(station, CoastStation) and station.reconstructed
        ]

    def official_gauge_levels_at(self, event_t: int) -> list[OfficialGaugeLevel]:
        """What each recorded Official Gauge reads at this Event time, in the mesh format."""
        elapsed = event_t - self.start_unix
        return [
            OfficialGaugeLevel(
                agency=gauge.agency,
                station=gauge.station,
                level_m=round(gauge.level_at(elapsed), 3),
                observed=event_t,
                mode="replay",
            )
            for gauge in self.official_gauges
        ]

    def readings_at(self, spot: SensorSpot, event_t: int, timestamp: datetime) -> list[Reading]:
        """What a Sensor at `spot` reads at this Event time; a dry spot sends no `water_level`."""
        elapsed = event_t - self.start_unix
        weather = _interpolate(
            elapsed,
            [(w.t, (w.rain_mmh, w.soil_pct, w.pressure_hpa)) for w in self.weather],
        )
        measurements: list[tuple[str, float, str, int]] = [
            ("air_pressure", weather[2], "hPa", 1),
            ("rain_rate", weather[0], "mm/h", 1),
            ("soil_moisture", weather[1], "%", 1),
        ]
        water_m = self.surface.level_at(spot, elapsed)
        if water_m is not None:
            measurements.append(("water_level", water_m, "m", 3))
        return [
            Reading(kind=kind, value=round(value, decimals), unit=unit, timestamp=timestamp)
            for kind, value, unit, decimals in measurements
        ]

    def _seconds_after_start(self, clock_time: str) -> int:
        return _seconds_in_day(clock_time) - _seconds_in_day(self.start)


def _interpolate(at: float, points: Sequence[tuple[float, tuple[float, ...]]]) -> tuple[float, ...]:
    """The values at `at`, on straight lines between points sorted by position; held beyond the ends."""
    if at <= points[0][0]:
        return points[0][1]
    for (before_at, before), (after_at, after) in itertools.pairwise(points):
        if at <= after_at:
            progress = (at - before_at) / (after_at - before_at)
            return tuple(a + (b - a) * progress for a, b in zip(before, after, strict=True))
    return points[-1][1]


def _seconds_in_day(clock_time: str) -> int:
    hours, minutes, seconds = (int(part) for part in clock_time.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def read_event_file(path: Path) -> Event:
    """The Event in `path`; a file that does not fit raises RegionError naming each bad field."""
    try:
        return Event.model_validate(json.loads(path.read_text()))
    except OSError as error:
        raise RegionError(f"cannot read Event file {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise RegionError(f"{path} is not JSON: {error}") from error
    except ValidationError as error:
        raise RegionError(f"{path}:\n{describe_problems(error)}") from error


def load_events(region: Region) -> dict[str, Event]:
    """Every Event file of the Region, by id, in file-name order; the first is the one a stopped
    Node reads. Raises RegionError when there is none, or one does not fit the Region."""
    folder = events_dir(region.name)
    events = [read_event_file(path) for path in sorted(folder.glob("*.json"))]
    if not events:
        raise RegionError(f"the {region.name} Region has no Events in {folder}")
    for event in events:
        event.require_fits(region)
    return {event.id: event for event in events}
