import hashlib
import io
import json
import zipfile
from typing import Any

SHELTERS = [
    {
        "id": "test-gym",
        "name": "Test Gym",
        "pos": [27.97857, 85.18407],
        "height_above_river_m": 96,
        "special_needs": True,
        "pet_friendly": False,
    }
]
FLOOD_PRONE = {"type": "FeatureCollection", "features": []}
RIVER = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"reach": "border to Betrawati", "speed_kmh": 68, "km": [44.5, 45.0]},
            "geometry": {"type": "LineString", "coordinates": [[85.18, 27.98], [85.186, 27.9731]]},
        }
    ],
}
WEATHER_REPLAY = {"source": "fixture", "credit": "fixture credit", "times": ["2026-08-26T00:00Z"]}
TILE = b"\x89PNG fixture tile"
TILE_PATH = "tiles/10/754/429.png"
WEATHER_PATH = "weather_replay.json"
NEPAL_BORDER_PATH = "nepal/border.geojson"
NEPAL_BORDER = {"type": "FeatureCollection", "features": []}
ELEVATION_PATH = "elevation/5/24/13.png"
ELEVATION_TILE = b"\x89PNG fixture elevation"
NEPAL_ENTRY = {
    "bbox": [26.3, 80.0, 30.5, 88.3],
    "elevation": {
        "encoding": "terrarium",
        "approximate": True,
        "national_zooms": [5, 5],
        "detail_zooms": [9, 9],
        "detail_areas": [[27.86, 85.08, 28.46, 85.47]],
    },
    "sources": [
        {"layer": "border", "name": "fixture", "licence": "CC BY 4.0", "checked": "2026-10-18"}
    ],
}


def build_nepal_pack(
    *,
    corrupt_tile: bool = False,
    leave_out_tile: bool = False,
    with_weather: bool = False,
    corrupt_weather: bool = False,
    with_nepal: bool = False,
    corrupt_nepal: bool = False,
    shelters: list[dict[str, object]] = SHELTERS,
    region_file: bytes | None = None,
) -> bytes:
    """A tiny Nepal Cache Pack in the real layout; the flags break it in the ways a download can
    break.

    Nepal because the only Replay is the Bhote Koshi's, on a river. Tests move to the Fort Myers
    fixture pack (`fort_myers_pack.py`) once the coast water surface exists (#48, then #90).
    """
    files = {
        "shelters.json": json.dumps(shelters).encode(),
        "flood_prone.geojson": json.dumps(FLOOD_PRONE).encode(),
        "river.geojson": json.dumps(RIVER).encode(),
        TILE_PATH: TILE,
    }
    if region_file is not None:
        files["region.json"] = region_file
    if with_weather:
        files[WEATHER_PATH] = json.dumps(WEATHER_REPLAY).encode()
    if with_nepal:
        files[NEPAL_BORDER_PATH] = json.dumps(NEPAL_BORDER).encode()
        files[ELEVATION_PATH] = ELEVATION_TILE
    manifest: dict[str, Any] = {
        "v": 1,
        "built": "2026-10-16T00:00:00Z",
        "bbox": [27.86, 85.08, 28.46, 85.47],
        "files": {path: hashlib.sha256(content).hexdigest() for path, content in files.items()},
    }
    if with_nepal:
        manifest["nepal"] = NEPAL_ENTRY
    if corrupt_nepal:
        files[ELEVATION_PATH] = b"tampered"
    if corrupt_tile:
        files[TILE_PATH] = b"tampered"
    if corrupt_weather:
        files[WEATHER_PATH] = b"tampered"
    if leave_out_tile:
        del files[TILE_PATH]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()
