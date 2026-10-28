"""Build a Region's Cache Pack from regions/<name>/region.json. See scripts/cache-pack/README.md."""

import argparse
import hashlib
import json
import sys
import zipfile
import zlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from http_retry import describe_error
from pack_basemap import fetch_basemap
from pack_flood_prone import trace_flood_prone_area
from pack_high_ground import build_high_ground
from pack_routes import FloodProneArea, Point, Roads, RouteGrid, build_road_graph, build_routes
from pack_sources import SourceFailed, is_address, read_source
import pack_terrain
from pack_terrain import fetch_terrain
from pack_weather import build_weather_replay

from storm_shield.region import REGIONS_DIR, Region, RegionError, River, load_region
from storm_shield.replay import Event, read_event_file
from storm_shield.terrain import elevation_at
from storm_shield.weather_grid import BBox

# Pis pull the whole pack over the mesh, so routes stay small; the grid coarsens until they fit.
ROUTE_SPACINGS_M = (100, 250, 500)
ROUTES_BUDGET_BYTES = 5_000_000
USER_AGENT = "storm-shield-cache-pack-builder/1.0 (SwampHacks 2026 student project)"
DOWNLOAD_TIMEOUT_SECONDS = 60


def download_osm_extract(url: str, destination: Path) -> None:
    print(f"downloading the OpenStreetMap extract to {destination}", flush=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Beside the final name, so an interrupted download is not mistaken for the extract next run.
    partial = destination.with_name(destination.name + ".part")
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_bytes():
                    file.write(chunk)
    except httpx.HTTPError as error:
        raise SourceFailed(f"OpenStreetMap extract failed: {describe_error(error)}") from None
    partial.rename(destination)


def osm_extract_of(region: Region, region_dir: Path, work_dir: Path) -> Path:
    """The Region's OpenStreetMap extract: its file, or the download kept in `work_dir`."""
    url = region.sources.roads.url
    if not is_address(url):
        extract = region_dir / url
    else:
        extract = work_dir / f"{region.name}-roads.osm.pbf"
        if not extract.is_file():
            download_osm_extract(url, extract)
    if not extract.is_file():
        raise SourceFailed(f"roads: cannot read {extract}")
    return extract


def load_roads(osm_extract: Path, bbox: BBox) -> Roads:
    from pyrosm import OSM  # build-only dependency: `uv run --with pyrosm`

    south, west, north, east = bbox
    nodes, edges = OSM(str(osm_extract), bounding_box=[west, south, east, north]).get_network(
        network_type="driving", nodes=True
    )
    coords = {
        int(node_id): (lat, lon)
        for node_id, lat, lon in zip(nodes["id"], nodes["lat"], nodes["lon"], strict=True)
    }
    # pyrosm cuts every way into one edge per pair of consecutive OSM nodes. The Road graph
    # ignores one-way rules, but Routes honour them. A driveway or parking aisle is no way to a
    # Shelter.
    segments = []
    for start, end, kind, oneway in zip(
        edges["u"], edges["v"], edges["highway"], edges["oneway"], strict=True
    ):
        if start in coords and end in coords and kind != "service":
            if str(oneway) == "-1":
                segments.append((int(end), int(start), True))
            else:
                segments.append((int(start), int(end), str(oneway) == "yes"))
    return Roads(coords, segments)


def build_route_files(
    roads: Roads,
    shelter_points: dict[str, Point],
    avoid: FloodProneArea,
    bbox: BBox,
) -> tuple[RouteGrid, dict[str, bytes]]:
    for spacing_m in ROUTE_SPACINGS_M:
        grid = RouteGrid.spaced(bbox, spacing_m)
        routes = build_routes(roads, shelter_points, grid, bbox, avoid)
        files = {
            path: json.dumps(by_shelter, separators=(",", ":")).encode()
            for path, by_shelter in routes.items()
        }
        compressed = sum(len(zlib.compress(content)) for content in files.values())
        print(f"{len(files)} route files at {spacing_m} m: {compressed / 1e6:.1f} MB", flush=True)
        if compressed <= ROUTES_BUDGET_BYTES:
            return grid, files
    raise SourceFailed(
        f"routes stay over {ROUTES_BUDGET_BYTES / 1e6:.0f} MB even at {ROUTE_SPACINGS_M[-1]} m"
    )


def read_events(region: Region, region_dir: Path) -> dict[str, tuple[Event, bytes]]:
    """Every Event file of the Region, checked against the Event schema and the Region's alert
    sources; each with its bytes, by id."""
    events = {}
    for path in sorted((region_dir / "events").glob("*.json")):
        event = read_event_file(path)
        event.require_fits(region)
        events[event.id] = (event, path.read_bytes())
    return events


def weather_days(events: list[Event]) -> tuple[str, str]:
    """The first and last UTC day to record: the day before the earliest Event to the day after
    the latest, so a replay in any time zone has weather for every hour."""
    days = [date.fromisoformat(event.date) for event in events]
    return (min(days) - timedelta(days=1)).isoformat(), (max(days) + timedelta(days=1)).isoformat()


def build(region_dir: Path, output: Path, work_dir: Path, client: httpx.Client) -> None:
    """Write the Cache Pack of the Region in `region_dir` to `output`.

    Raises RegionError for a Region or Event file that does not fit its schema, and SourceFailed
    (or ValueError for data that fails a check) naming the source that failed.
    """
    region_file = region_dir / "region.json"
    region = load_region(region_file)
    events = read_events(region, region_dir)
    bbox = region.bbox
    sources = region.sources
    shelters = [
        shelter.model_dump(exclude={"source"}, exclude_none=True) for shelter in region.shelters
    ]

    files: dict[str, bytes] = {
        "region.json": region_file.read_bytes(),
        "shelters.json": json.dumps(shelters, indent=1).encode(),
        **{f"events/{event_id}.json": raw for event_id, (_, raw) in events.items()},
    }

    print(f"reading the {region.label} basemap", flush=True)
    basemap = fetch_basemap(client, region_dir, sources.basemap, bbox)
    files.update(basemap)
    print("reading the terrain", flush=True)
    terrain = fetch_terrain(client, region_dir, sources.terrain, bbox)
    files.update(terrain)

    water = region.water
    if isinstance(water, River):
        files["flood_prone.geojson"] = read_source(
            client, region_dir, water.corridor_source, "flood corridor"
        )
        files["river.geojson"] = read_source(client, region_dir, water.line_source, "river line")
    else:
        print("tracing the Flood-Prone Area from the terrain", flush=True)
        traced = trace_flood_prone_area(
            lambda lat, lon: elevation_at(terrain.get, lat, lon),
            bbox,
            water.flood_prone_below.cm / 100,
        )
        files["flood_prone.geojson"] = json.dumps(traced, separators=(",", ":")).encode()
    flood_prone = FloodProneArea.from_geojson(json.loads(files["flood_prone.geojson"]))
    flooded_shelters = [
        shelter.id for shelter in region.shelters if flood_prone.contains(shelter.pos)
    ]
    if flooded_shelters:
        raise ValueError(
            f"Shelters inside the Flood-Prone Area: {', '.join(flooded_shelters)}; move them out "
            "or drop them"
        )

    real_events = [event for event, _ in events.values() if event.real]
    if real_events:
        first_day, last_day = weather_days(real_events)
        print(f"reading the weather of {first_day} to {last_day}", flush=True)
        weather = build_weather_replay(
            client, region_dir, sources.weather, bbox, first_day, last_day
        )
        files["weather_replay.json"] = json.dumps(weather, separators=(",", ":")).encode()

    river_vertices: list[Point] = []
    if isinstance(water, River):
        river_vertices = [
            (lat, lon)
            for line in json.loads(files["river.geojson"])["features"]
            for lon, lat in line["geometry"]["coordinates"]
        ]
    high_ground = build_high_ground(
        [point.model_dump() for point in region.high_ground],
        river_vertices,
        flood_prone,
        lambda lat, lon: elevation_at(terrain.get, lat, lon),
    )
    files["high_ground.json"] = json.dumps(high_ground, indent=1).encode()
    print(f"high ground: {len(high_ground)} points")

    extract = osm_extract_of(region, region_dir, work_dir)
    try:
        roads = load_roads(extract, bbox)
    except Exception as error:  # pyrosm raises whatever the damaged file trips on
        raise SourceFailed(f"roads: cannot read {extract}: {type(error).__name__}") from None
    shelter_points = {shelter.id: shelter.pos for shelter in region.shelters}
    graph = build_road_graph(roads, list(shelter_points.values()))
    files["roads.json"] = json.dumps(graph, separators=(",", ":")).encode()
    print(f"road graph: {len(graph['nodes'])} junctions, {len(graph['edges'])} segments")
    route_grid, route_files = build_route_files(roads, shelter_points, flood_prone, bbox)
    files.update(route_files)

    checked = date.today().isoformat()
    manifest = {
        "v": 1,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "region": region.name,
        "bbox": list(bbox),
        "route_grid": route_grid.as_manifest_entry(),
        "terrain": pack_terrain.manifest_entry(),
        "sources": [
            {"layer": layer, "credit": source.credit, "checked": checked}
            for layer, source in (
                ("terrain", sources.terrain),
                ("roads", sources.roads),
                ("basemap", sources.basemap),
                ("weather", sources.weather),
            )
        ],
        "files": {path: hashlib.sha256(content).hexdigest() for path, content in files.items()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=1))
        for path, content in files.items():
            archive.writestr(path, content)
    print(f"wrote {output} ({output.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("region", help="the folder under regions/ to build, e.g. nepal")
    parser.add_argument("--output", type=Path, help="default: build/<region>/cache-pack.zip")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("build"),
        help="where the OpenStreetMap extract is kept between builds (default: build)",
    )
    arguments = parser.parse_args()
    region_dir = REGIONS_DIR / arguments.region
    if not (region_dir / "region.json").is_file():
        known = sorted(path.parent.name for path in REGIONS_DIR.glob("*/region.json"))
        sys.exit(f"no Region called {arguments.region!r}; the Regions are: {', '.join(known)}")
    output = arguments.output or Path("build") / arguments.region / "cache-pack.zip"
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=DOWNLOAD_TIMEOUT_SECONDS) as client:
            build(region_dir, output, arguments.work_dir, client)
    except (RegionError, SourceFailed, ValueError) as error:
        sys.exit(f"build failed: {error}")


if __name__ == "__main__":
    main()
