"""The Fort Myers fixture pack: a small Cache Pack the tests use instead of the published one.

It holds the real `regions/fort-myers/region.json`, the Shelters drawn from it as the build draws
them, and an empty Flood-Prone Area: what a Node reads from a pack, and nothing a test would have to
fetch. The zip is checked in at `FIXTURE_PACK`; after a change to the Region file, rebuild it from
`node/` with `uv run python tests/fort_myers_pack.py` (a test fails until you do).
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

REGION_FILE = Path(__file__).resolve().parents[2] / "regions" / "fort-myers" / "region.json"
FIXTURE_PACK = Path(__file__).resolve().parent / "fixtures" / "fort-myers" / "cache-pack.zip"
# Fixed, so building twice from the same Region file gives the same bytes.
BUILT = "2026-10-24T00:00:00+00:00"
ZIP_TIME = (2026, 10, 24, 0, 0, 0)


def build_fort_myers_pack(
    terrain: dict[str, bytes] | None = None, region_file: Path = REGION_FILE
) -> bytes:
    """The fixture pack's bytes, built from the Region file as it is now; a test that needs ground
    heights adds its own `terrain` tiles, keyed by pack path. A test that needs another Region's
    pack passes that Region's `region_file`."""
    raw_region = region_file.read_bytes()
    region: dict[str, Any] = json.loads(raw_region)
    # As scripts/build_cache_pack.py writes them: each Shelter without its reviewers' note.
    shelters = [
        {key: value for key, value in shelter.items() if key != "source" and value is not None}
        for shelter in region["shelters"]
    ]
    files = {
        "region.json": raw_region,
        "shelters.json": json.dumps(shelters, indent=1).encode(),
        "flood_prone.geojson": json.dumps({"type": "FeatureCollection", "features": []}).encode(),
        **(terrain or {}),
    }
    manifest = {
        "v": 1,
        "built": BUILT,
        "region": region["name"],
        "bbox": region["bbox"],
        "files": {path: hashlib.sha256(content).hexdigest() for path, content in files.items()},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo("manifest.json", ZIP_TIME), json.dumps(manifest, indent=1))
        for path, content in files.items():
            archive.writestr(zipfile.ZipInfo(path, ZIP_TIME), content)
    return buffer.getvalue()


if __name__ == "__main__":
    FIXTURE_PACK.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PACK.write_bytes(build_fort_myers_pack())
    print(f"wrote {FIXTURE_PACK} ({FIXTURE_PACK.stat().st_size} bytes)")
