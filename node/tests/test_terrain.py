import pytest
from terrarium import png, terrarium_png

from storm_shield.terrain import decode_rgb, elevation_at, tile_position


def test_the_png_reader_undoes_the_sub_and_up_filters() -> None:
    rows = [[(10, 20, 30), (11, 22, 33), (200, 100, 50)], [(12, 21, 31), (15, 25, 35), (1, 2, 3)]]
    for filter_type in (0, 1, 2):
        decoded = decode_rgb(png(rows, filter_type))
        assert decoded == (3, 2, 3, bytes(v for row in rows for pixel in row for v in pixel))


def test_elevation_is_read_from_the_finest_tile_holding_the_point() -> None:
    x, y = tile_position(1.5, 1.5, 9)
    fine_x, fine_y = tile_position(1.5, 1.5, 12)
    tiles = {
        f"elevation/9/{int(x)}/{int(y)}.png": terrarium_png(100),
        f"elevation/12/{int(fine_x)}/{int(fine_y)}.png": terrarium_png(1400),
    }
    assert elevation_at(tiles.get, 1.5, 1.5) == 1400
    with pytest.raises(ValueError, match="no elevation tile"):
        no_tiles: dict[str, bytes] = {}
        elevation_at(no_tiles.get, 1.5, 1.5)
