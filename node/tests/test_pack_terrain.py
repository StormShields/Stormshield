from pathlib import Path

import httpx
import pack_terrain
import pytest
from pack_sources import SourceFailed
from pack_terrain import fetch_terrain, tiles_covering
from terrarium import terrarium_png

from storm_shield import terrain
from storm_shield.region import Source

BBOX = (27.86, 85.08, 28.46, 85.47)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"a local source was fetched from {request.url}")


NO_NETWORK = httpx.Client(transport=httpx.MockTransport(_refuse))


def test_tiles_covering_cover_the_box_at_each_zoom() -> None:
    paths = tiles_covering(BBOX, range(9, 11))
    assert {zoom for zoom, _, _ in paths} == {9, 10}
    assert (10, 754, 428) in paths


@pytest.fixture
def quick_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack_terrain, "DELAY_SECONDS", 0)


def test_tiles_are_read_from_the_template_under_the_regions_folder(
    tmp_path: Path, quick_tiles: None
) -> None:
    bbox = (1.0, 1.0, 1.01, 1.01)
    for zoom, x, y in tiles_covering(bbox, terrain.ZOOMS):
        tile = tmp_path / "terrain" / str(zoom) / str(x) / f"{y}.png"
        tile.parent.mkdir(parents=True, exist_ok=True)
        tile.write_bytes(terrarium_png(5))
    source = Source(url="terrain/{z}/{x}/{y}.png", credit="test")

    tiles = fetch_terrain(NO_NETWORK, tmp_path, source, bbox)

    assert {path.split("/")[1] for path in tiles} == {"9", "10", "11", "12"}
    assert all(path.endswith(".png") for path in tiles)


def test_a_missing_tile_names_itself(tmp_path: Path, quick_tiles: None) -> None:
    source = Source(url="terrain/{z}/{x}/{y}.png", credit="test")
    with pytest.raises(SourceFailed, match="terrain tile 9/"):
        fetch_terrain(NO_NETWORK, tmp_path, source, (1.0, 1.0, 1.01, 1.01))


def test_tiles_over_budget_fail_the_build(
    tmp_path: Path, quick_tiles: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    bbox = (1.0, 1.0, 1.01, 1.01)
    for zoom, x, y in tiles_covering(bbox, terrain.ZOOMS):
        tile = tmp_path / str(zoom) / str(x) / f"{y}.png"
        tile.parent.mkdir(parents=True, exist_ok=True)
        tile.write_bytes(terrarium_png(5))
    monkeypatch.setattr(pack_terrain, "BUDGET_BYTES", 10)
    source = Source(url="{z}/{x}/{y}.png", credit="test")
    with pytest.raises(SourceFailed, match="budget"):
        fetch_terrain(NO_NETWORK, tmp_path, source, bbox)
