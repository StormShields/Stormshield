import hashlib
import io
import json
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRY_EVERY_SECONDS = 30
DOWNLOAD_TIMEOUT_SECONDS = 60
REQUIRED_FILES = ("shelters.json", "flood_prone.geojson")
ZIP_NAME = "cache-pack.zip"
UNPACKED_DIR = "files"
RELEASES_URL = "https://github.com/StormShields/Stormshield/releases/download"
# The version of each built-in Region's pack published as the Release `cache-pack-<region>-v<N>`
# (scripts/cache-pack/README.md): publishing a new version means changing its number here.
RELEASED_PACKS = {"nepal": 1, "fort-myers": 2}


class InvalidCachePack(Exception):
    pass


def release_url(region: str) -> str | None:
    """Where the Region's pack is published, or None for a Region with no Release."""
    version = RELEASED_PACKS.get(region)
    if version is None:
        return None
    return f"{RELEASES_URL}/cache-pack-{region}-v{version}/{ZIP_NAME}"


def download_source(override: str, region: str) -> str:
    """Where a Node fetches its pack: `override` (CACHE_PACK_URL) when set, else the Region's
    Release. Empty when there is nowhere to fetch from."""
    return override or release_url(region) or ""


def _is_safe_relative_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(parts) and not PurePosixPath(path).is_absolute() and ".." not in parts


def _read_manifest(raw: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(raw)
        files = manifest["files"]
        if manifest["v"] != 1 or not isinstance(files, dict):
            raise InvalidCachePack("unsupported manifest")
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidCachePack(f"unreadable manifest: {error}") from error
    for name in REQUIRED_FILES:
        if name not in files:
            raise InvalidCachePack(f"manifest lists no {name}")
    if not all(_is_safe_relative_path(path) for path in files):
        raise InvalidCachePack("manifest lists a path outside the pack")
    return dict(manifest)


def _check_checksum(path: str, content: bytes, expected: str) -> None:
    if hashlib.sha256(content).hexdigest() != expected:
        raise InvalidCachePack(f"{path} does not match its checksum")


class CachePack:
    """The Cache Pack kept on this Node's disk: downloaded once, verified, served from disk."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._unpacked = directory / UNPACKED_DIR
        self._manifest = self._verify_disk()

    @property
    def zip_path(self) -> Path:
        return self._directory / ZIP_NAME

    @property
    def manifest(self) -> dict[str, Any] | None:
        """The manifest of the pack on disk, or None when this Node has no valid pack."""
        return self._manifest

    def file(self, path: str) -> Path | None:
        """A file listed in the manifest, or None. Never a path the manifest does not list."""
        if self._manifest is None or path not in self._manifest["files"]:
            return None
        return self._unpacked / path

    def shelter_ids(self) -> list[str]:
        """The id of every Shelter in the pack, or an empty list when this Node has no valid pack."""
        shelters = self.file("shelters.json")
        if shelters is None:
            return []
        return [shelter["id"] for shelter in json.loads(shelters.read_bytes())]

    def _verify_disk(self) -> dict[str, Any] | None:
        if not self._unpacked.exists() and not self.zip_path.exists():
            return None
        try:
            manifest = _read_manifest((self._unpacked / "manifest.json").read_bytes())
            for path, checksum in manifest["files"].items():
                _check_checksum(path, (self._unpacked / path).read_bytes(), checksum)
            if not self.zip_path.is_file():
                raise InvalidCachePack("the zip for other Nodes is missing")
        except (OSError, InvalidCachePack) as error:
            logger.warning("discarding the Cache Pack on disk: %s", error)
            self._discard()
            return None
        return manifest

    def install(self, zip_bytes: bytes) -> None:
        """Verify a downloaded pack and keep it. Raises InvalidCachePack and keeps nothing if it is bad."""
        try:
            archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
            manifest = _read_manifest(archive.read("manifest.json"))
            contents = {path: archive.read(path) for path in manifest["files"]}
        except (zipfile.BadZipFile, KeyError) as error:
            raise InvalidCachePack(f"incomplete pack: {error}") from error
        for path, content in contents.items():
            _check_checksum(path, content, manifest["files"][path])

        self._discard()
        staging = self._directory / f"{UNPACKED_DIR}.staging"
        shutil.rmtree(staging, ignore_errors=True)
        for path, content in {**contents, "manifest.json": archive.read("manifest.json")}.items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (self._directory / ZIP_NAME).write_bytes(zip_bytes)
        staging.rename(self._unpacked)
        self._manifest = manifest

    def _discard(self) -> None:
        self._manifest = None
        shutil.rmtree(self._unpacked, ignore_errors=True)
        self.zip_path.unlink(missing_ok=True)

    def download(self, url: str, client: httpx.Client) -> None:
        response = client.get(url)
        response.raise_for_status()
        self.install(response.content)
