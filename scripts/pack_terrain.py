"""The Region's terrain for the Cache Pack: Terrarium elevation tiles over its bbox."""

import time
from pathlib import Path

import httpx
from pack_sources import SourceFailed, read_source
from storm_shield.region import Source
from storm_shield.terrain import ZOOMS, tile_position
from storm_shield.weather_grid import BBox

# Only for the elevation tiles (PNGs do not compress); the vector layers are small.
BUDGET_BYTES = 10_000_000
DELAY_SECONDS = 0.05


def tiles_covering(bbox: BBox, zooms: range) -> list[tuple[int, int, int]]:
    """Every (z, x, y) web-mercator tile touching `bbox`."""
    south, west, north, east = bbox
    tiles = []
    for zoom in zooms:
        x_min, y_max = (int(value) for value in tile_position(south, west, zoom))
        x_max, y_min = (int(value) for value in tile_position(north, east, zoom))
        tiles += [(zoom, x, y) for x in range(x_min, x_max + 1) for y in range(y_min, y_max + 1)]
    return tiles


def manifest_entry() -> dict[str, object]:
    return {"encoding": "terrarium", "approximate": True, "zooms": [ZOOMS.start, ZOOMS.stop - 1]}


def fetch_terrain(
    client: httpx.Client, region_dir: Path, source: Source, bbox: BBox
) -> dict[str, bytes]:
    """Terrarium tiles for every zoom over `bbox`, keyed `elevation/{z}/{x}/{y}.png`.

    Raises SourceFailed when a tile cannot be read or the tiles go over the budget.
    """
    tiles = {}
    for zoom, x, y in tiles_covering(bbox, ZOOMS):
        location = source.url.format(z=zoom, x=x, y=y)
        tiles[f"elevation/{zoom}/{x}/{y}.png"] = read_source(
            client, region_dir, location, f"terrain tile {zoom}/{x}/{y}"
        )
        time.sleep(DELAY_SECONDS)
    total = sum(len(content) for content in tiles.values())
    if total > BUDGET_BYTES:
        raise SourceFailed(
            f"terrain tiles are {total / 1e6:.1f} MB, over the {BUDGET_BYTES / 1e6:.1f} MB budget"
        )
    return tiles
