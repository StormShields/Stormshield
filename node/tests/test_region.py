import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fixture_pack import nepal_event
from meshed_nodes import MeshedNodes

from storm_shield import region as region_module
from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.region import (
    Coast,
    CoastFloodWarningRules,
    FloodWarningRules,
    RegionError,
    events_dir,
    load_region,
    region_path,
)
from storm_shield.settings import Settings

NEPAL = region_path("nepal")
NEPAL_EVENTS = events_dir("nepal")


def _write_region(folder: Path, name: str = "fixture", **changes: Any) -> Path:
    """A Region file under `folder` made from Nepal's with `changes` merged in, beside a copy of
    Nepal's Events; its path."""
    region = json.loads(NEPAL.read_text()) | {"name": name} | changes
    shutil.copytree(NEPAL_EVENTS, folder / name / "events")
    path = folder / name / "region.json"
    path.write_text(json.dumps(region))
    return path


def _flash_flood(**changes: Any) -> dict[str, Any]:
    """Nepal's flood-warning rules with `changes` applied to the flash-flood block."""
    rules = json.loads(NEPAL.read_text())["rules"]["flood_warning"]
    rules["flash_flood"] |= changes
    return {"rules": {"flood_warning": rules}}


def _surged(client: TestClient) -> list[str]:
    surged: list[str] = client.get("/api/state").json()["flood_risk"]["surged"]
    return surged


def test_nepals_region_holds_what_the_app_used_to_hard_wire() -> None:
    region = load_region(NEPAL)
    rules = region.rules.flood_warning
    assert isinstance(rules, FloodWarningRules)
    assert region.hazard == "flash_flood"
    assert region.time_zone == "Asia/Kathmandu"
    assert (rules.flash_flood.surge_rise.cm, rules.flash_flood.surge_window_s) == (300, 60)
    assert (rules.flash_flood.elevated_level.cm, rules.flash_flood.high_level.cm) == (300, 600)
    assert (rules.rain_elevated.mm_per_hour, rules.rain_high.mm_per_hour) == (10, 25)
    assert rules.storm_pressure.hpa == 1000
    assert [site.id for site in region.sensor_sites] == ["s3", "s2", "s1", "s0"]
    assert len(region.shelters) == 5


def test_thresholds_are_converted_from_the_units_they_are_written_in(tmp_path: Path) -> None:
    path = _write_region(tmp_path, **_flash_flood(surge_rise={"value": 10, "unit": "ft"}))
    rules = load_region(path).rules.flood_warning
    assert isinstance(rules, FloodWarningRules)
    assert rules.flash_flood.surge_rise.cm == pytest.approx(304.8)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"time_zone": "Mars/Olympus"}, "time_zone"),
        ({"bbox": [28.0, 85.0, 27.0, 86.0]}, "bbox"),
        ({"surprise": 1}, "surprise"),
        (_flash_flood(surge_rise={"value": 3, "unit": "furlongs"}), "surge_rise.unit"),
        (_flash_flood(surge_window_s=0), "surge_window_s"),
        (_flash_flood(surge_window_s=300), "flash_flood"),
        ({"official_alert_sources": []}, "official_alert_sources"),
    ],
)
def test_a_bad_region_file_names_the_bad_field(
    tmp_path: Path, changes: dict[str, Any], field: str
) -> None:
    path = _write_region(tmp_path, **changes)
    with pytest.raises(RegionError) as error:
        load_region(path)
    assert field in str(error.value)


def test_a_sensor_site_outside_the_box_is_named(tmp_path: Path) -> None:
    sites = json.loads(NEPAL.read_text())["sensor_sites"]
    sites[1]["pos"] = [0.0, 0.0]
    path = _write_region(tmp_path, sensor_sites=sites)
    with pytest.raises(RegionError, match=r"sensor_sites\[1\]"):
        load_region(path)


def test_a_hub_site_outside_the_box_is_named(tmp_path: Path) -> None:
    hub_site = json.loads(NEPAL.read_text())["hub_site"] | {"pos": [0.0, 0.0]}
    path = _write_region(tmp_path, hub_site=hub_site)
    with pytest.raises(RegionError, match="hub_site"):
        load_region(path)


def test_a_node_will_not_start_on_a_bad_region_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_region(tmp_path, time_zone="Mars/Olympus")
    monkeypatch.setattr(region_module, "REGIONS_DIR", tmp_path)
    settings = Settings(name="porch", region="fixture", dashboard_dir=tmp_path / "none")
    mesh = InMemoryNetwork().join("porch", "hub")
    with pytest.raises(RegionError, match="time_zone"):
        create_app(settings, mesh)


def test_an_event_alert_from_a_source_the_region_does_not_list_stops_the_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = [{"tag": "dhm", "name": "DHM", "covers": "Nepal"}]
    assert nepal_event().official_alerts[-1].issuer == "district"
    _write_region(tmp_path, official_alert_sources=sources)
    monkeypatch.setattr(region_module, "REGIONS_DIR", tmp_path)
    settings = Settings(name="porch", region="fixture", dashboard_dir=tmp_path / "none")
    mesh = InMemoryNetwork().join("porch", "hub")
    with pytest.raises(RegionError, match="district"):
        create_app(settings, mesh)


def test_the_regions_surge_rise_decides_when_the_warning_fires(
    meshed_nodes: MeshedNodes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A 200 cm rise: calm for Nepal's 300 cm, a Surge for a Region that asks for 150 cm.
    meshed_nodes.start("nepal-like")
    _write_region(tmp_path, **_flash_flood(surge_rise={"value": 1.5, "unit": "m"}))
    monkeypatch.setattr(region_module, "REGIONS_DIR", tmp_path)
    meshed_nodes.start("fixture-like", region="fixture")
    for name in ("nepal-like", "fixture-like"):
        meshed_nodes.register("creek", name)
        meshed_nodes.hear_from("creek", water_cm=20)
        meshed_nodes.advance(8)
        meshed_nodes.hear_from("creek", water_cm=220)
    assert _surged(meshed_nodes["nepal-like"]) == []
    assert _surged(meshed_nodes["fixture-like"]) == ["creek"]


FORT_MYERS = region_path("fort-myers")


def _write_coast_region(folder: Path, **changes: Any) -> Path:
    """Fort Myers's file with `changes` merged in; its path."""
    region = json.loads(FORT_MYERS.read_text()) | changes
    (folder / "coast").mkdir(parents=True)
    path = folder / "coast" / "region.json"
    path.write_text(json.dumps(region))
    return path


def test_fort_myers_is_a_coast_region_read_in_feet_and_miles() -> None:
    region = load_region(FORT_MYERS)
    rules = region.rules.flood_warning
    assert isinstance(rules, CoastFloodWarningRules)
    assert isinstance(region.water, Coast)
    assert (region.hazard, region.water.datum) == ("storm_surge", "NAVD88")
    assert region.water.flood_prone_below.cm == pytest.approx(9 * 30.48)
    assert region.time_zone == "America/New_York"
    assert (region.display_units.water_level, region.display_units.distance) == ("ft", "mi")
    assert rules.storm_surge.warning_height.cm == pytest.approx(3 * 30.48)
    assert [source.tag for source in region.official_alert_sources] == ["nws_tbw"]
    assert [gauge.station for gauge in region.official_gauges] == ["8725520"]
    assert all(shelter.height_above_river_m is None for shelter in region.shelters)
    assert region.high_ground == []
    assert region.summary().water_type == "coast"
    # The Hub runs in a Shelter, which is dry ground where people gather.
    assert region.hub_site.pos in [shelter.pos for shelter in region.shelters]


@pytest.mark.parametrize(
    ("changes", "complaint"),
    [
        (
            {"rules": {"flood_warning": json.loads(NEPAL.read_text())["rules"]["flood_warning"]}},
            "storm_surge",
        ),
        (
            {
                "shelters": [
                    {**json.loads(FORT_MYERS.read_text())["shelters"][0], "height_above_river_m": 5}
                ]
            },
            "height_above_river_m",
        ),
        ({"high_ground": json.loads(NEPAL.read_text())["high_ground"]}, "high_ground"),
        (
            {
                "water": {
                    "type": "coast",
                    "datum": "NGVD29",
                    "flood_prone_below": {"value": 9, "unit": "ft"},
                }
            },
            "datum",
        ),
        (
            {
                "official_gauges": [
                    {**json.loads(FORT_MYERS.read_text())["official_gauges"][0], "pos": [0, 0]}
                ]
            },
            r"official_gauges\[0\]",
        ),
    ],
)
def test_a_coast_region_file_that_does_not_hang_together_is_refused(
    tmp_path: Path, changes: dict[str, Any], complaint: str
) -> None:
    with pytest.raises(RegionError, match=complaint):
        load_region(_write_coast_region(tmp_path, **changes))


def test_a_river_shelter_needs_its_height_above_the_river(tmp_path: Path) -> None:
    shelters = json.loads(NEPAL.read_text())["shelters"]
    del shelters[0]["height_above_river_m"]
    with pytest.raises(RegionError, match="height_above_river_m"):
        load_region(_write_region(tmp_path, shelters=shelters))


def test_a_node_on_a_coast_region_will_not_play_a_flash_flood(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "regions"
    shutil.copytree(NEPAL_EVENTS, folder / "fort-myers" / "events")
    (folder / "fort-myers" / "region.json").write_text(FORT_MYERS.read_text())
    monkeypatch.setattr(region_module, "REGIONS_DIR", folder)
    settings = Settings(name="porch", region="fort-myers", dashboard_dir=tmp_path / "none")
    with pytest.raises(RegionError, match="is a flash_flood"):
        create_app(settings, InMemoryNetwork().join("porch", "hub"))
