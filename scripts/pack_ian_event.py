"""Generate the Hurricane Ian Event of the Fort Myers Region from its checked-in sources.

Writes regions/fort-myers/events/ian-2022.json, which the Cache Pack build then carries. Reads only
the files in regions/fort-myers/sources/, so it never touches the network. Run it again only when
those files change: `uv run --project node python scripts/pack_ian_event.py`.
"""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from storm_shield.region import REGIONS_DIR, Region, load_region

WATER_LEVEL_FILE = "noaa-8725520-fort-myers-water-level.csv"
WARNINGS_FILE = "nws-tbw-warnings-2022-09.csv"
GAUGE_STATION = "8725520"
FEET_IN_METRES = 0.3048

EVENT_DATE = "2022-09-28"
START = "06:00:00"
END = "21:00:00"
DEFAULT_RATE = 30
# NHC's Ian report (AL092022): the peak at Fort Myers Beach Pier, feet above MHHW.
BEACH_PEAK_FEET_MHHW = 12.7
# The stations whose series is the gauge's curve scaled to that peak, not a record.
RECONSTRUCTED_STATIONS = (
    ("fort-myers-beach-pier", "Fort Myers Beach Pier", (26.4507, -81.9533)),
    ("estero-bay", "Estero Bay at Coconut Point Marina", (26.39993, -81.84036)),
)
# NWS Tampa Bay zones for Lee County: coastal and inland.
LEE_COUNTY_ZONES = {"FLZ165", "FLZ265"}
ALERT_ISSUER = "nws_tbw"
PHENOMENA = {
    "SS": "Storm Surge",
    "HU": "Hurricane",
    "TR": "Tropical Storm",
    "FL": "Flood",
    "FA": "Flood",
    "FF": "Flash Flood",
}
SIGNIFICANCE = {"A": "Watch", "W": "Warning"}
SOURCES = {
    "noaa-8725520": "https://tidesandcurrents.noaa.gov/stationhome.html?id=8725520",
    "nhc-ian-report": "https://www.nhc.noaa.gov/data/tcr/AL092022_Ian.pdf",
    "nws-tbw-warnings": "https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml",
}
LANDFALL = "15:05:00"

# Not measured: the Weather Grid records no soil moisture or pressure, so a Sensor's rain, soil and
# pressure follow these hand-set keyframes (seconds after 06:00, rain mm/h, soil %, pressure hPa),
# shaped like a hurricane passing: the pressure falls to landfall and the rain peaks after it.
WEATHER_KEYFRAMES = (
    (0, 2, 85, 1000),
    (4 * 3600, 12, 90, 985),
    (9 * 3600, 30, 95, 962),
    (11 * 3600, 20, 97, 968),
    (15 * 3600, 3, 97, 985),
)


def _csv_rows(text: str) -> list[dict[str, str]]:
    """The rows keyed by header, with the stray spaces NOAA leaves around names and values gone."""
    return [
        {key.strip(): value.strip() for key, value in row.items() if key is not None}
        for row in csv.DictReader(io.StringIO(text))
    ]


def _utc(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _series(
    readings: list[tuple[int, float]], scale: float, offset_m: float
) -> list[list[float]]:
    return [
        [at, round(level_feet * scale * FEET_IN_METRES + offset_m, 3)]
        for at, level_feet in readings
    ]


def _offset_text(moment: datetime) -> str:
    """The UTC offset the Event files write: "-04:00"."""
    offset = moment.strftime("%z")
    return f"{offset[:3]}:{offset[3:]}"


def build_ian_event(region: Region, water_level_csv: str, warnings_csv: str) -> dict[str, Any]:
    """The Event file: the gauge and the scaled stations in the Region's datum, the Official Alerts
    in force over the window, and the recorded gauge for the Official Gauge to play."""
    zone = ZoneInfo(region.time_zone)
    start = datetime.fromisoformat(f"{EVENT_DATE}T{START}").replace(tzinfo=zone)
    end = datetime.fromisoformat(f"{EVENT_DATE}T{END}").replace(tzinfo=zone)
    gauge = next(each for each in region.official_gauges if each.station == GAUGE_STATION)
    offset_m = gauge.datum_offset.cm / 100

    # Feet above MHHW against seconds after the start; a blank reading is skipped.
    recorded = [
        (int((_utc(row["Date Time"]) - start).total_seconds()), float(row["Water Level"]))
        for row in _csv_rows(water_level_csv)
        if row["Water Level"] and start <= _utc(row["Date Time"]) <= end
    ]
    peak_at, peak_feet = max(recorded, key=lambda reading: reading[1])
    gauge_series = _series(recorded, 1, offset_m)
    scale = BEACH_PEAK_FEET_MHHW / peak_feet
    stations = [
        {
            "id": "fort-myers-gauge",
            "label": gauge.label,
            "pos": list(gauge.pos),
            "reconstructed": False,
            "series": gauge_series,
        },
        *(
            {
                "id": station_id,
                "label": label,
                "pos": list(pos),
                "reconstructed": True,
                "series": _series(recorded, scale, offset_m),
            }
            for station_id, label, pos in RECONSTRUCTED_STATIONS
        ),
    ]

    alerts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _csv_rows(warnings_csv):
        issued = _utc(row["utc_issue"])
        in_force = issued < end and _utc(row["utc_expire"]) > start
        kept = row["ugc"] in LEE_COUNTY_ZONES and row["phenomena"] in PHENOMENA
        if not (in_force and kept and row["significance"] in SIGNIFICANCE):
            continue
        # The coastal and inland zones get one notice, so they make one alert.
        key = (row["utc_issue"], row["phenomena"], row["significance"])
        local = issued.astimezone(zone)
        headline = f"{PHENOMENA[row['phenomena']]} {SIGNIFICANCE[row['significance']]}"
        alerts[key] = {
            "id": f"nws-tbw-{row['phenomena']}{row['significance']}-{issued:%Y%m%d%H%M}z".lower(),
            "date": local.date().isoformat(),
            "at": local.strftime("%H:%M:%S"),
            "issuer": ALERT_ISSUER,
            "headline": headline,
            "applies_to": [],
            "source": "nws-tbw-warnings",
        }
    official_alerts = sorted(alerts.values(), key=lambda alert: (alert["date"], alert["at"]))

    peak_local = start + timedelta(seconds=peak_at)
    return {
        "id": "ian-2022",
        "label": "Hurricane Ian storm surge",
        "hazard": "storm_surge",
        "real": True,
        "note": (
            "The Fort Myers gauge is the record. Fort Myers Beach Pier and Estero Bay are that "
            "curve scaled to NHC's reported 12.7 ft above MHHW peak, not recorded, and in this "
            "version of the curve their peak comes at the gauge's peak time. Rain, soil moisture "
            "and pressure are hand-set to the shape of a hurricane passing, not measured."
        ),
        "date": EVENT_DATE,
        "utc_offset": _offset_text(start),
        "start": START,
        "end": END,
        "start_unix": int(start.timestamp()),
        "rate": DEFAULT_RATE,
        "sources": SOURCES,
        "phases": [
            {"id": "approach", "at": START, "label": "Ian approaches the coast"},
            {"id": "landfall", "at": LANDFALL, "label": "Landfall at Cayo Costa"},
            {
                "id": "surge-peak",
                "at": peak_local.strftime("%H:%M:%S"),
                "label": "Surge peaks at the Fort Myers gauge",
            },
            {"id": "end", "at": END, "label": "End of the replay"},
        ],
        "internet_cue": {
            "at": LANDFALL,
            "note": "Placed at landfall; no source says when connections failed in Lee County.",
        },
        "official_alerts": official_alerts,
        "official_gauges": [
            {"agency": gauge.agency, "station": gauge.station, "series": gauge_series}
        ],
        "surface": {"datum": "NAVD88", "unit": "m", "stations": stations},
        "weather_note": (
            "The Weather Grid over the window plays on the map; a Sensor's rain, soil moisture and "
            "pressure follow these hand-set keyframes, which are not measurements."
        ),
        "weather": [
            {"t": at, "rain_mmh": rain, "soil_pct": soil, "pressure_hpa": pressure}
            for at, rain, soil, pressure in WEATHER_KEYFRAMES
        ],
    }


def read_ian_event_sources(region_dir: Path) -> tuple[str, str]:
    """The water-level and warnings files of the Region's `sources/` folder."""
    sources = region_dir / "sources"
    return (sources / WATER_LEVEL_FILE).read_text(), (sources / WARNINGS_FILE).read_text()


def main() -> None:
    region_dir = REGIONS_DIR / "fort-myers"
    region = load_region(region_dir / "region.json")
    event = build_ian_event(region, *read_ian_event_sources(region_dir))
    destination = region_dir / "events" / "ian-2022.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(event, indent=1) + "\n")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
