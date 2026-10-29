"""The Ian Event generated from the Fort Myers sources: the water in the Region's datum, the Official
Alerts of Lee County, and the recorded gauge."""

from typing import Any

import pytest
from pack_ian_event import build_ian_event, read_ian_event_sources

from storm_shield.region import load_region, region_path
from storm_shield.replay import Event, read_event_file

REGION = load_region(region_path("fort-myers"))
FEET = 0.3048
GAUGE_OFFSET_M = REGION.official_gauges[0].datum_offset.cm / 100

# 28 Sep 2022 is 10:00 to 01:00 UTC for the 06:00 to 21:00 Eastern window.
WATER_CSV = """Date Time, Water Level, Sigma, O or I (for verified), F, R, L, Quality
2022-09-28 09:54,0.9,0.01,0,0,0,0,v
2022-09-28 10:00,1.0,0.01,0,0,0,0,v
2022-09-28 10:06,2.0,0.01,0,0,0,0,v
2022-09-28 10:12,,0.01,0,0,0,0,v
2022-09-28 22:30,7.257,0.01,0,0,0,0,v
2022-09-29 01:00,3.0,0.01,0,0,0,0,v
2022-09-29 01:06,2.5,0.01,0,0,0,0,v
"""
# Two USGS storm sensors: readings every 30 s in metres above NAVD88, the beach rising from 10:00 UTC
# and the bay only reporting from 10:12, with a reading before the window and one after it.
SENSOR_CSV = """instrument_id,site_number,time_utc,water_level_m_navd88
10768,FLLEE03382,2022-09-28 09:55:00,0.400
10768,FLLEE03382,2022-09-28 10:00:00,0.500
10768,FLLEE03382,2022-09-28 10:00:30,0.510
10768,FLLEE03382,2022-09-28 10:06:00,1.500
10768,FLLEE03382,2022-09-28 18:00:00,4.000
10768,FLLEE03382,2022-09-29 01:00:00,2.000
10768,FLLEE03382,2022-09-29 01:06:00,1.000
10855,FLLEE03289,2022-09-28 10:12:00,0.700
10855,FLLEE03289,2022-09-28 19:24:00,3.600
"""
WARNINGS_HEADER = "wfo,utc_issue,utc_expire,phenomena,significance,eventid,status,ugc"


def warnings_csv(*rows: str) -> str:
    return "\n".join([WARNINGS_HEADER, *rows]) + "\n"


def build(warnings: str = warnings_csv(), sensors: str = SENSOR_CSV) -> Event:
    return Event.model_validate(build_ian_event(REGION, WATER_CSV, warnings, sensors))


def alert_headlines(event: Event) -> list[str]:
    return [alert.headline for alert in event.official_alerts]


def station(event: Event, station_id: str) -> Any:
    return next(each for each in event.surface.stations if each.id == station_id)


def test_the_gauge_series_is_in_the_regions_datum_in_metres() -> None:
    gauge = station(build(), "fort-myers-gauge")

    assert not gauge.reconstructed
    assert gauge.series[0] == (0, pytest.approx(1.0 * FEET + GAUGE_OFFSET_M, abs=1e-3))
    assert gauge.series[1] == (360, pytest.approx(2.0 * FEET + GAUGE_OFFSET_M, abs=1e-3))


def test_the_series_keeps_only_the_window_and_skips_missing_readings() -> None:
    gauge = station(build(), "fort-myers-gauge")

    assert [at for at, _ in gauge.series] == [0, 360, 12.5 * 3600, 15 * 3600]


def test_a_usgs_storm_sensor_plays_every_reading_of_the_window() -> None:
    beach = station(build(), "fort-myers-beach-pier")

    assert not beach.reconstructed
    assert beach.label == "Fort Myers Beach Pier"
    assert beach.pos == (26.4523944, -81.95665833)
    # Metres above NAVD88 as the USGS wrote them, with no datum offset added; the readings outside
    # the window are left out.
    assert beach.series == [(0, 0.5), (30, 0.51), (360, 1.5), (8 * 3600, 4.0), (15 * 3600, 2.0)]


def test_a_sensor_that_reports_late_starts_its_series_when_it_does() -> None:
    bay = station(build(), "coconut-point-marina")

    assert not bay.reconstructed
    assert bay.series[0] == (720, 0.7)


def test_a_station_with_no_readings_in_the_file_is_not_in_the_event() -> None:
    event = build()

    assert [each.id for each in event.surface.stations] == [
        "fort-myers-gauge",
        "fort-myers-beach-pier",
        "coconut-point-marina",
    ]


def test_no_station_of_the_committed_ian_event_is_reconstructed() -> None:
    event = read_event_file(region_path("fort-myers").parent / "events" / "ian-2022.json")

    assert event.reconstructed_station_labels() == []
    assert {each.id for each in event.surface.stations} == {
        "fort-myers-gauge",
        "fort-myers-beach-pier",
        "matanzas-pass",
        "lovers-key-big-carlos-pass",
        "coconut-point-marina",
        "san-carlos-bay-punta-rassa",
        "mullock-creek-marina",
    }


def test_the_beach_peaks_at_the_recorded_height_and_hours_before_the_gauge() -> None:
    event = read_event_file(region_path("fort-myers").parent / "events" / "ian-2022.json")

    beach_at, beach_peak = max(station(event, "fort-myers-beach-pier").series, key=lambda r: r[1])
    gauge_at, _ = max(station(event, "fort-myers-gauge").series, key=lambda r: r[1])
    # USGS storm sensor 10768 recorded 4.03 m above NAVD88 at 18:39 UTC, 14:39 Eastern.
    assert beach_peak == pytest.approx(4.03, abs=0.05)
    assert beach_at == pytest.approx(8.65 * 3600, abs=360)
    assert gauge_at - beach_at > 3 * 3600


def test_the_recorded_gauge_plays_as_an_official_gauge() -> None:
    event = build()

    gauge = event.official_gauges[0]
    assert (gauge.agency, gauge.station) == ("NOAA", "8725520")
    assert gauge.series == station(event, "fort-myers-gauge").series


def test_official_alerts_are_lee_county_zones_and_the_kept_phenomena_in_force_in_the_window() -> (
    None
):
    event = build(
        warnings_csv(
            "TBW,2022-09-27 09:08,2022-09-29 09:10,HU,W,1009,CAN,FLZ165",
            "TBW,2022-09-27 09:08,2022-09-29 09:10,HU,W,1009,CAN,FLZ265",
            "TBW,2022-09-26 21:10,2022-09-29 12:25,SS,W,1009,CAN,FLZ165",
            "TBW,2022-09-28 16:36,2022-09-28 23:00,FF,W,5,NEW,FLZ265",
            "TBW,2022-09-28 12:00,2022-09-28 13:00,TO,W,7,NEW,FLZ165",
            "TBW,2022-09-28 12:00,2022-09-28 13:00,FF,W,8,NEW,FLC015",
            "TBW,2022-09-26 21:10,2022-09-27 09:08,TR,W,1009,UPG,FLZ165",
            "TBW,2022-09-29 09:10,2022-09-29 15:30,TR,W,1009,CAN,FLZ165",
        )
    )

    assert alert_headlines(event) == [
        "Storm Surge Warning",
        "Hurricane Warning",
        "Flash Flood Warning",
    ]


def test_an_alert_is_at_its_issue_time_in_eastern_time() -> None:
    event = build(warnings_csv("TBW,2022-09-28 16:36,2022-09-28 23:00,FF,W,5,NEW,FLZ265"))

    alert = event.official_alerts[0]
    assert (alert.date, alert.at, alert.issuer) == ("2022-09-28", "12:36:00", "nws_tbw")
    assert event.event_t_at(alert.at) == event.start_unix + 6 * 3600 + 36 * 60


def test_an_alert_issued_before_the_window_keeps_its_own_day() -> None:
    event = build(warnings_csv("TBW,2022-09-27 09:08,2022-09-29 09:10,HU,W,1009,CAN,FLZ165"))

    alert = event.official_alerts[0]
    assert (alert.date, alert.at) == ("2022-09-27", "05:08:00")
    assert event.official_alerts_due(event.start_unix)[0].issued == "2022-09-27T05:08:00-04:00"


def test_a_watch_and_a_warning_of_one_kind_are_two_alerts() -> None:
    event = build(
        warnings_csv(
            "TBW,2022-09-28 12:00,2022-09-28 20:00,FA,A,3,NEW,FLZ165",
            "TBW,2022-09-28 14:00,2022-09-28 22:00,FA,W,4,NEW,FLZ165",
        )
    )

    assert alert_headlines(event) == ["Flood Watch", "Flood Warning"]


def test_the_event_fits_the_region_and_names_its_phases() -> None:
    event = build()

    event.require_fits(REGION)
    assert (event.id, event.hazard, event.date, event.utc_offset) == (
        "ian-2022",
        "storm_surge",
        "2022-09-28",
        "-04:00",
    )
    assert [phase.label for phase in event.phases][1] == "Landfall at Cayo Costa"


def test_the_committed_ian_event_is_what_the_sources_build() -> None:
    region_dir = region_path("fort-myers").parent
    built = Event.model_validate(build_ian_event(REGION, *read_ian_event_sources(region_dir)))

    assert read_event_file(region_dir / "events" / "ian-2022.json") == built
