"""The Cache Pack build on a tiny fixture Region whose sources are all local files."""

import hashlib
import json
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import build_cache_pack
import http_retry
import httpx
import pack_routes
import pack_terrain
import pytest
from pack_routes import FloodProneArea, Point, Roads
from pack_sources import SourceFailed
from terrarium import terrarium_png

from storm_shield.region import RegionError, region_path
from storm_shield.weather_grid import grid_points

NEPAL = region_path("nepal").parent
FORT_MYERS = region_path("fort-myers").parent
BBOX = (1.0, 1.0, 1.2, 1.2)
RIVER_LAT = 1.1
HILLTOP = (1.17, 1.15)
SHELTER = (1.18, 1.15)
HOURS = ["2026-08-25T00:00", "2026-08-25T01:00"]
OVERPASS_ANSWER = {
    "elements": [
        {"type": "node", "lat": 1.17, "lon": 1.16, "tags": {"place": "village", "name": "Hilltop"}},
        {
            "type": "way",
            "tags": {"highway": "residential", "name": "Main Street"},
            "geometry": [{"lat": 1.18, "lon": 1.0}, {"lat": 1.18, "lon": 1.2}],
        },
        {
            "type": "way",
            "tags": {"waterway": "river", "name": "Mud River"},
            "geometry": [{"lat": RIVER_LAT, "lon": 1.05}, {"lat": RIVER_LAT, "lon": 1.15}],
        },
    ]
}


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"a local source was fetched from {request.url}")


NO_NETWORK = httpx.Client(transport=httpx.MockTransport(_refuse))


def _archive_answer() -> list[dict[str, Any]]:
    _, _, points = grid_points(BBOX)
    return [
        {
            "hourly": {
                "time": HOURS,
                "temperature_2m": [20.0, 21.0],
                "cloud_cover": [10, 20],
                "precipitation": [0.0, 0.5],
            }
        }
        for _ in points
    ]


def _write(path: Path, content: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content))


def _write_terrain(
    region_dir: Path, height_of_tile: Callable[[Callable[[Point], bool]], int]
) -> None:
    """One Terrarium tile per tile of the box at every zoom; `height_of_tile` is given a test for
    whether the tile holds a point and answers the tile's height in metres."""
    for zoom, x, y in pack_terrain.tiles_covering(BBOX, pack_terrain.ZOOMS):

        def holds(point: Point, zoom: int = zoom, x: int = x, y: int = y) -> bool:
            point_x, point_y = pack_terrain.tile_position(*point, zoom)
            return (x, y) == (int(point_x), int(point_y))

        tile = region_dir / "sources" / "terrain" / str(zoom) / str(x) / f"{y}.png"
        tile.parent.mkdir(parents=True, exist_ok=True)
        tile.write_bytes(terrarium_png(height_of_tile(holds)))


def _fixture_region(folder: Path, **changes: Any) -> Path:
    """A Region folder: Nepal's rules and Event around a one-Shelter box whose sources are files."""
    region_dir = folder / "fixture"
    nepal = json.loads((NEPAL / "region.json").read_text())
    region = {
        **nepal,
        "name": "fixture",
        "label": "Fixture valley",
        "bbox": list(BBOX),
        "water": {
            "type": "river",
            "km_origin": [RIVER_LAT, 1.05],
            "line_source": "sources/river.geojson",
            "corridor_source": "sources/corridor.geojson",
        },
        "shelters": [
            {
                "id": "gym",
                "name": "Gym",
                "pos": list(SHELTER),
                "height_above_river_m": 90,
                "special_needs": True,
                "pet_friendly": False,
                "source": "a note for reviewers",
            }
        ],
        "high_ground": [
            {
                "id": "ridge",
                "name": "Ridge",
                "pos": list(HILLTOP),
                "town": "Hilltop",
                "town_pos": [1.17, 1.16],
                "source": "from the tiles",
                "checked": "2026-10-20",
            }
        ],
        "sensor_sites": [],
        "hub_site": {"id": "hub", "label": "Gym", "pos": list(SHELTER), "why": "inside the box"},
        "sources": {
            "terrain": {"url": "sources/terrain/{z}/{x}/{y}.png", "credit": "terrain credit"},
            "roads": {"url": "sources/roads.osm.pbf", "credit": "roads credit"},
            "basemap": {"url": "sources/overpass.json", "credit": "basemap credit"},
            "weather": {"url": "sources/weather.json", "credit": "weather credit"},
        },
    } | changes
    _write(region_dir / "region.json", region)
    _write(region_dir / "sources" / "overpass.json", OVERPASS_ANSWER)
    _write(region_dir / "sources" / "weather.json", _archive_answer())
    _write(
        region_dir / "sources" / "river.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[1.05, RIVER_LAT], [1.15, RIVER_LAT]],
                    },
                }
            ],
        },
    )
    band = [[1.04, 1.095], [1.16, 1.095], [1.16, 1.105], [1.04, 1.105], [1.04, 1.095]]
    _write(
        region_dir / "sources" / "corridor.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [band]},
                }
            ],
        },
    )
    (region_dir / "sources" / "roads.osm.pbf").write_bytes(b"not read: load_roads is replaced")
    # The hilltop's tiles read 200 m and every other tile 10 m, so it climbs 190 m above the river.
    _write_terrain(region_dir, lambda tile_holds: 200 if tile_holds(HILLTOP) else 10)
    shutil.copytree(NEPAL / "events", region_dir / "events")
    return region_dir


@pytest.fixture(autouse=True)
def offline_and_quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack_terrain, "DELAY_SECONDS", 0)
    monkeypatch.setattr(http_retry, "RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(build_cache_pack, "ROUTE_SPACINGS_M", (1000,))
    road = Roads({1: (1.18, 1.0), 2: SHELTER, 3: (1.18, 1.2)}, [(1, 2, False), (2, 3, False)])
    monkeypatch.setattr(build_cache_pack, "load_roads", lambda extract, bbox: road)


def _build(tmp_path: Path, region_dir: Path, client: httpx.Client = NO_NETWORK) -> zipfile.ZipFile:
    output = tmp_path / "out" / "cache-pack.zip"
    build_cache_pack.build(region_dir, output, tmp_path / "work", client)
    return zipfile.ZipFile(output)


def _json(archive: zipfile.ZipFile, path: str) -> Any:
    return json.loads(archive.read(path))


def test_the_pack_holds_the_regions_file_and_everything_built_from_it(tmp_path: Path) -> None:
    region_dir = _fixture_region(tmp_path)

    pack = _build(tmp_path, region_dir)

    assert pack.read("region.json") == (region_dir / "region.json").read_bytes()
    assert [shelter["id"] for shelter in _json(pack, "shelters.json")] == ["gym"]
    assert "source" not in _json(pack, "shelters.json")[0]
    assert _json(pack, "flood_prone.geojson")["features"][0]["geometry"]["type"] == "Polygon"
    assert _json(pack, "river.geojson")["features"][0]["geometry"]["type"] == "LineString"
    [ridge] = _json(pack, "high_ground.json")
    assert (ridge["id"], ridge["town"], ridge["climb_m"]) == ("ridge", "Hilltop", 190)
    assert _json(pack, "roads.json")["nodes"]
    names = pack.namelist()
    assert any(name.startswith("routes/") for name in names)
    assert "events/bhote-koshi-2026.json" in names
    assert any(name.startswith("elevation/12/") for name in names)


def test_the_basemap_comes_from_the_openstreetmap_answer_not_from_nepal(tmp_path: Path) -> None:
    pack = _build(tmp_path, _fixture_region(tmp_path))

    [road] = _json(pack, "basemap/roads.geojson")["features"]
    assert road["properties"]["name"] == "Main Street"
    assert _json(pack, "basemap/waterways.geojson")["features"][0]["properties"]["name"] == (
        "Mud River"
    )
    assert _json(pack, "basemap/places.geojson")["features"][0]["properties"]["name"] == "Hilltop"
    assert not [name for name in pack.namelist() if name.startswith("nepal/")]


def test_the_weather_grid_covers_the_regions_box_and_the_days_around_the_event(
    tmp_path: Path,
) -> None:
    pack = _build(tmp_path, _fixture_region(tmp_path))

    grid = _json(pack, "weather_replay.json")["grid"]
    rows, cols, _ = grid_points(BBOX)
    assert (grid["south"], grid["west"], grid["rows"], grid["cols"]) == (1.0, 1.0, rows, cols)


def test_the_weather_is_asked_for_the_day_before_to_the_day_after_the_event(
    tmp_path: Path,
) -> None:
    asked: list[dict[str, str]] = []

    def archive(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=_archive_answer())

    region_dir = _fixture_region(tmp_path)
    region = json.loads((region_dir / "region.json").read_text())
    region["sources"]["weather"]["url"] = "https://archive.example/v1/archive"
    (region_dir / "region.json").write_text(json.dumps(region))

    _build(tmp_path, region_dir, httpx.Client(transport=httpx.MockTransport(archive)))

    assert (asked[0]["start_date"], asked[0]["end_date"]) == ("2026-08-25", "2026-08-27")


def test_the_manifest_names_the_region_the_terrain_and_checksums_every_file(
    tmp_path: Path,
) -> None:
    pack = _build(tmp_path, _fixture_region(tmp_path))

    manifest = _json(pack, "manifest.json")
    assert (manifest["v"], manifest["region"], manifest["bbox"]) == (1, "fixture", list(BBOX))
    assert manifest["terrain"] == {"encoding": "terrarium", "approximate": True, "zooms": [9, 12]}
    assert {source["layer"]: source["credit"] for source in manifest["sources"]} == {
        "terrain": "terrain credit",
        "roads": "roads credit",
        "basemap": "basemap credit",
        "weather": "weather credit",
    }
    assert set(manifest["files"]) == set(pack.namelist()) - {"manifest.json"}
    for path, checksum in manifest["files"].items():
        assert hashlib.sha256(pack.read(path)).hexdigest() == checksum
    assert set(manifest["route_grid"]) == {"south", "west", "lat_step", "lon_step"}
    assert pack_routes.RouteGrid.spaced(BBOX, 1000).as_manifest_entry() == manifest["route_grid"]


def test_a_bad_region_field_is_named(tmp_path: Path) -> None:
    region_dir = _fixture_region(tmp_path, time_zone="Mars/Olympus")
    with pytest.raises(RegionError, match="time_zone"):
        _build(tmp_path, region_dir)


def test_a_bad_event_field_is_named(tmp_path: Path) -> None:
    region_dir = _fixture_region(tmp_path)
    event_file = region_dir / "events" / "bhote-koshi-2026.json"
    event = json.loads(event_file.read_text())
    event["rate"] = "fast"
    event_file.write_text(json.dumps(event))
    with pytest.raises(RegionError, match=r"bhote-koshi-2026\.json:\n  rate"):
        _build(tmp_path, region_dir)


def test_an_event_alert_from_a_source_the_region_does_not_list_is_refused(
    tmp_path: Path,
) -> None:
    region_dir = _fixture_region(
        tmp_path, official_alert_sources=[{"tag": "dhm", "name": "DHM", "covers": "Nepal"}]
    )
    with pytest.raises(RegionError, match="district"):
        _build(tmp_path, region_dir)


def test_a_missing_terrain_tile_says_which_source_failed(tmp_path: Path) -> None:
    region_dir = _fixture_region(tmp_path)
    next((region_dir / "sources" / "terrain").rglob("*.png")).unlink()
    with pytest.raises(SourceFailed, match="terrain tile"):
        _build(tmp_path, region_dir)


def test_a_basemap_server_that_stays_down_says_so_without_its_address(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    region_dir = _fixture_region(tmp_path)
    region = json.loads((region_dir / "region.json").read_text())
    region["sources"]["basemap"]["url"] = "https://overpass.example/api?key=secret"
    (region_dir / "region.json").write_text(json.dumps(region))

    with pytest.raises(SourceFailed) as problem:
        _build(tmp_path, region_dir, httpx.Client(transport=httpx.MockTransport(down)))

    assert "OpenStreetMap basemap failed 5 times, last HTTP 502" in str(problem.value)
    assert "secret" not in str(problem.value)


def test_a_high_ground_point_far_from_its_town_fails_the_build(tmp_path: Path) -> None:
    region_dir = _fixture_region(tmp_path)
    region = json.loads((region_dir / "region.json").read_text())
    region["high_ground"][0]["town_pos"] = [1.02, 1.02]
    (region_dir / "region.json").write_text(json.dumps(region))
    with pytest.raises(ValueError, match="high-ground point ridge is over 2000 m from Hilltop"):
        _build(tmp_path, region_dir)


SEA = (1.01, 1.01)
LOW_GROUND = (1.1, 1.1)


def _coast_region(folder: Path, shelter: tuple[float, float] = SHELTER) -> Path:
    """The fixture box as a coast Region (Fort Myers's water and rules) whose terrain is sea in the
    south-west tile, 6 m at the Shelter's tile and 1 m everywhere else."""
    fort_myers = json.loads((FORT_MYERS / "region.json").read_text())
    gym = {
        "id": "gym",
        "name": "Gym",
        "pos": list(shelter),
        "special_needs": True,
        "pet_friendly": False,
        "source": "a note for reviewers",
    }
    region_dir = _fixture_region(
        folder,
        water=fort_myers["water"],
        rules=fort_myers["rules"],
        shelters=[gym],
        high_ground=[],
    )
    shutil.rmtree(region_dir / "events")
    _write_terrain(region_dir, lambda holds: 6 if holds(SHELTER) else 0 if holds(SEA) else 1)
    return region_dir


def test_a_coast_pack_traces_its_flood_prone_area_from_the_terrain(tmp_path: Path) -> None:
    pack = _build(tmp_path, _coast_region(tmp_path))

    traced = _json(pack, "flood_prone.geojson")
    assert traced["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert traced["features"][0]["properties"]["approximate"] is True
    area = FloodProneArea.from_geojson(traced)
    assert area.contains(LOW_GROUND)
    assert not area.contains(SHELTER)
    assert not area.contains(SEA)
    assert "river.geojson" not in pack.namelist()
    assert _json(pack, "high_ground.json") == []
    assert set(_json(pack, "shelters.json")[0]) == {
        "id",
        "name",
        "pos",
        "special_needs",
        "pet_friendly",
    }


def test_the_flood_prone_area_stops_at_the_regions_height(tmp_path: Path) -> None:
    region_dir = _coast_region(tmp_path)
    region = json.loads((region_dir / "region.json").read_text())
    region["water"]["flood_prone_below"] = {"value": 2, "unit": "ft"}
    (region_dir / "region.json").write_text(json.dumps(region))

    area = FloodProneArea.from_geojson(_json(_build(tmp_path, region_dir), "flood_prone.geojson"))

    assert not area.contains(LOW_GROUND)  # 1 m is over 2 ft (0.6 m)


def test_a_shelter_inside_the_flood_prone_area_fails_the_build(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Shelters inside the Flood-Prone Area: gym"):
        _build(tmp_path, _coast_region(tmp_path, shelter=LOW_GROUND))
