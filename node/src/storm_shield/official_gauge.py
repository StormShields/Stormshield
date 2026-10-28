import logging
import threading
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel

from storm_shield.region import OfficialGauge

logger = logging.getLogger(__name__)

NOAA_WATER_LEVEL_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_TIMEOUT_SECONDS = 20
# NOAA's own datum for a station's levels; the Region's `datum_offset` turns it into the Region's.
NOAA_DATUM = "MHHW"


class OfficialGaugeLevel(BaseModel):
    """An Official Gauge's latest level in the mesh format of docs/specs/wire-formats.md; only the Hub sends one."""

    v: Literal[1] = 1
    kind: Literal["gauge"] = "gauge"
    agency: Literal["NOAA"]
    station: str
    # Metres in the Region's datum, like a Community Reading's water level.
    level_m: float
    # When the agency measured it, Unix seconds.
    observed: int


class HeardOfficialGauges:
    """The newest level this Node has heard from the Hub for each of the Region's Official Gauges."""

    def __init__(self, gauges: list[OfficialGauge]) -> None:
        self._known = {(gauge.agency, gauge.station) for gauge in gauges}
        # The Reticulum receive thread writes while request threads read.
        self._lock = threading.Lock()
        self._newest: dict[tuple[str, str], OfficialGaugeLevel] = {}

    def hear(self, level: OfficialGaugeLevel) -> None:
        """Keep the level only if it is newer, so a repeated old copy can't undo a later one."""
        key = (level.agency, level.station)
        if key not in self._known:
            return
        with self._lock:
            held = self._newest.get(key)
            if held is None or level.observed > held.observed:
                self._newest[key] = level

    def newest(self, gauge: OfficialGauge) -> OfficialGaugeLevel | None:
        with self._lock:
            return self._newest.get((gauge.agency, gauge.station))

    def all_newest(self) -> list[OfficialGaugeLevel]:
        with self._lock:
            return list(self._newest.values())


def read_noaa_level(source: httpx.Client, gauge: OfficialGauge) -> OfficialGaugeLevel | None:
    """The station's latest water level in the Region's datum, or None when NOAA has none.

    Raises httpx.HTTPError when NOAA cannot be reached, so the caller can tell "offline" from "no data".
    """
    answer = source.get(
        NOAA_WATER_LEVEL_URL,
        params={
            "product": "water_level",
            "date": "latest",
            "station": gauge.station,
            "datum": NOAA_DATUM,
            "units": "metric",
            "time_zone": "gmt",
            "format": "json",
            "application": "StormShield",
        },
    )
    answer.raise_for_status()
    rows = answer.json().get("data")
    # NOAA answers {"error": ...} with a 200 for a station with no recent data.
    if not rows:
        return None
    try:
        row = rows[-1]
        observed = datetime.strptime(row["t"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        level_m = float(row["v"]) + gauge.datum_offset.cm / 100
    except (KeyError, ValueError, TypeError):
        logger.warning("NOAA station %s answered something unreadable: %r", gauge.station, rows[-1])
        return None
    return OfficialGaugeLevel(
        agency=gauge.agency,
        station=gauge.station,
        level_m=round(level_m, 3),
        observed=int(observed.timestamp()),
    )
