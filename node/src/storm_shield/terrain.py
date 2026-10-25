"""Ground height from a Cache Pack's terrain: Terrarium elevation tiles, `elevation/{z}/{x}/{y}.png`.

The build reads them to trace the Flood-Prone Area; a Sensor reads them to know whether the water
reaches its spot.
"""

import math
import struct
import zlib
from collections.abc import Callable
from functools import lru_cache

# About 300 m a pixel at zoom 9 down to about 40 m at zoom 12: enough to read a home's ground.
ZOOMS = range(9, 13)


def tile_position(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """The point's place on the zoom's tile grid; the integer part is the tile, the rest is inside it."""
    n = 2**zoom
    return (
        (lon + 180) / 360 * n,
        (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n,
    )


@lru_cache(maxsize=32)
def decode_rgb(png: bytes) -> tuple[int, int, int, bytes]:
    """Width, height, bytes per pixel and the pixels of an 8-bit, non-interlaced RGB(A) PNG."""
    position, header, data = 8, b"", b""
    while position < len(png):
        (length,) = struct.unpack(">I", png[position : position + 4])
        kind, body = png[position + 4 : position + 8], png[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            data += body
        position += 12 + length
    width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", header)
    if depth != 8 or colour not in (2, 6) or interlace != 0:
        raise ValueError("elevation tiles must be 8-bit RGB(A), not interlaced")
    pixel = 3 if colour == 2 else 4
    stride, raw, rows = width * pixel, zlib.decompress(data), []
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        filter_type, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for i in range(stride):
            left = line[i - pixel] if i >= pixel else 0
            up = previous[i]
            up_left = previous[i - pixel] if i >= pixel else 0
            if filter_type == 1:
                line[i] = (line[i] + left) & 255
            elif filter_type == 2:
                line[i] = (line[i] + up) & 255
            elif filter_type == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif filter_type == 4:
                estimate = left + up - up_left
                nearest = min((abs(estimate - c), c) for c in (left, up, up_left))[1]
                line[i] = (line[i] + nearest) & 255
        rows.append(bytes(line))
        previous = line
    return width, height, pixel, b"".join(rows)


def elevation_at(tile: Callable[[str], bytes | None], lat: float, lon: float) -> float:
    """Metres above the terrain's datum at a point, from the finest Terrarium tile that holds it.

    `tile` gives a tile's bytes by its pack path, or None when the pack has no such tile. Raises
    ValueError when no tile covers the point.
    """
    for zoom in range(ZOOMS.stop - 1, ZOOMS.start - 1, -1):
        x, y = tile_position(lat, lon, zoom)
        png = tile(f"elevation/{zoom}/{int(x)}/{int(y)}.png")
        if png is not None:
            width, height, pixel, pixels = decode_rgb(png)
            offset = (int((y % 1) * height) * width + int((x % 1) * width)) * pixel
            red, green, blue = pixels[offset : offset + 3]
            return red * 256 + green + blue / 256 - 32768
    raise ValueError(f"no elevation tile covers {lat}, {lon}")
