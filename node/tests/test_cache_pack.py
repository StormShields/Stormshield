import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from fixture_pack import (
    ELEVATION_PATH,
    ELEVATION_TILE,
    FLOOD_PRONE,
    NEPAL_BORDER,
    NEPAL_BORDER_PATH,
    NEPAL_ENTRY,
    RIVER,
    SHELTERS,
    TILE,
    TILE_PATH,
    build_nepal_pack,
)

from storm_shield.cache_pack import RELEASED_PACKS, CachePack, download_source, release_url
from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.region import RegionError, region_path
from storm_shield.settings import Role, Settings


class PackSource:
    """A stand-in for the Release or the Hub: serves bytes until it is shut down."""

    def __init__(self, pack: bytes) -> None:
        self.pack = pack
        self.running = True
        self.requests = 0
        self.client = httpx.Client(transport=httpx.MockTransport(self._answer))

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if not self.running:
            raise httpx.ConnectError("the source is shut down", request=request)
        return httpx.Response(200, content=self.pack)


def _node(
    tmp_path: Path, source: httpx.Client, name: str = "node", url: str = "http://source/pack.zip"
) -> TestClient:
    settings = Settings(name=name, cache_pack_url=url, cache_pack_dir=tmp_path / name)
    return TestClient(create_app(settings, InMemoryNetwork().join(name), pack_source=source))


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the Cache Pack"
        time.sleep(0.02)


def _has_pack(client: TestClient) -> bool:
    return bool(client.get("/api/cache-pack").json()["available"])


def test_node_downloads_the_pack_and_serves_it_after_the_source_is_gone(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack())
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: _has_pack(node))
        source.running = False

        status = node.get("/api/cache-pack").json()
        assert status["manifest"]["bbox"] == [27.86, 85.08, 28.46, 85.47]
        assert node.get("/api/cache-pack/files/shelters.json").json() == SHELTERS
        assert node.get("/api/cache-pack/files/flood_prone.geojson").json() == FLOOD_PRONE
        assert node.get("/api/cache-pack/files/river.geojson").json() == RIVER
        assert node.get(f"/api/cache-pack/files/{TILE_PATH}").content == TILE


def test_node_serves_the_nepal_files_and_lists_their_sources(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(with_nepal=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: _has_pack(node))
        source.running = False

        assert node.get("/api/cache-pack").json()["manifest"]["nepal"] == NEPAL_ENTRY
        assert node.get(f"/api/cache-pack/files/{NEPAL_BORDER_PATH}").json() == NEPAL_BORDER
        assert node.get(f"/api/cache-pack/files/{ELEVATION_PATH}").content == ELEVATION_TILE


def test_a_pack_without_the_nepal_files_still_works(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack())
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: _has_pack(node))

        assert "nepal" not in node.get("/api/cache-pack").json()["manifest"]
        assert node.get(f"/api/cache-pack/files/{NEPAL_BORDER_PATH}").status_code == 404
        assert node.get(f"/api/cache-pack/files/{ELEVATION_PATH}").status_code == 404
        assert node.get("/api/cache-pack/files/river.geojson").json() == RIVER
        assert node.get("/api/shelters").status_code == 200


def test_a_pack_with_a_tampered_elevation_tile_is_refused(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(with_nepal=True, corrupt_nepal=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: source.requests >= 1)
        time.sleep(0.2)
        assert not _has_pack(node)
        assert not (tmp_path / "node" / "files").exists()


def test_pack_without_a_source_is_unavailable(tmp_path: Path) -> None:
    settings = Settings(cache_pack_dir=tmp_path / "empty")
    node = TestClient(create_app(settings, InMemoryNetwork().join(settings.name)))
    assert node.get("/api/cache-pack").json() == {"available": False, "manifest": None}
    assert node.get("/api/cache-pack.zip").status_code == 404
    assert node.get("/api/cache-pack/files/shelters.json").status_code == 404


def test_corrupt_pack_is_refused_and_discarded(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(corrupt_tile=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: source.requests >= 1)
        time.sleep(0.2)
        assert not _has_pack(node)
        assert not (tmp_path / "node" / "files").exists()


def test_incomplete_pack_is_refused(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(leave_out_tile=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: source.requests >= 1)
        time.sleep(0.2)
        assert not _has_pack(node)


def test_node_with_a_pack_on_disk_never_downloads_again(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack())
    with _node(tmp_path, source.client) as first:
        _wait_until(lambda: _has_pack(first))
    requests_so_far = source.requests

    with _node(tmp_path, source.client) as restarted:
        assert _has_pack(restarted)
        time.sleep(0.2)
    assert source.requests == requests_so_far


def test_pack_corrupted_on_disk_is_discarded_at_startup(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack())
    with _node(tmp_path, source.client) as first:
        _wait_until(lambda: _has_pack(first))
    (tmp_path / "node" / "files" / TILE_PATH).write_bytes(b"bit rot")

    source.running = False
    with _node(tmp_path, source.client) as restarted:
        assert not _has_pack(restarted)


def test_sensor_downloads_the_pack_from_a_hub_node(tmp_path: Path) -> None:
    release = PackSource(build_nepal_pack())
    with _node(tmp_path, release.client, name="hub") as hub:
        _wait_until(lambda: _has_pack(hub))
        release.running = False

        with _node(tmp_path, hub, name="sensor", url="/api/cache-pack.zip") as sensor:
            _wait_until(lambda: _has_pack(sensor))
            assert sensor.get(f"/api/cache-pack/files/{TILE_PATH}").content == TILE


def _pack_of_another_region(tmp_path: Path) -> Path:
    """A Node's pack directory holding a pack whose Region file has its own label."""
    region = json.loads(region_path("nepal").read_text()) | {"label": "The Hub's Region"}
    directory = tmp_path / "node"
    directory.mkdir()
    CachePack(directory).install(build_nepal_pack(region_file=json.dumps(region).encode()))
    return directory


@pytest.mark.parametrize(
    ("role", "label"), [("sensor", "The Hub's Region"), ("hub", "Bhote Koshi valley, Nepal")]
)
def test_a_sensor_takes_its_region_from_the_pack_and_a_hub_keeps_its_own(
    tmp_path: Path, role: Role, label: str
) -> None:
    settings = Settings(role=role, cache_pack_dir=_pack_of_another_region(tmp_path))
    node = TestClient(create_app(settings, InMemoryNetwork().join("node")))
    assert node.get("/api/state").json()["region"]["label"] == label


def test_a_pack_with_a_bad_region_file_stops_the_sensor_that_holds_it(tmp_path: Path) -> None:
    directory = tmp_path / "node"
    directory.mkdir()
    CachePack(directory).install(build_nepal_pack(region_file=b'{"name": "x"}'))
    with pytest.raises(RegionError, match="bbox"):
        create_app(Settings(cache_pack_dir=directory), InMemoryNetwork().join("node"))


def test_a_node_downloads_from_cache_pack_url_else_its_regions_release() -> None:
    assert download_source("http://hub:8000/api/cache-pack.zip", "nepal") == (
        "http://hub:8000/api/cache-pack.zip"
    )
    assert download_source("", "nepal") == release_url("nepal")
    assert release_url("nepal") == (
        "https://github.com/StormShields/Stormshield/releases/download/"
        f"cache-pack-nepal-v{RELEASED_PACKS['nepal']}/cache-pack.zip"
    )
    assert download_source("", "no-such-region") == ""


def test_node_region_chooses_the_release_a_hub_downloads_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NODE_REGION", "no-such-region")
    assert download_source("", Settings().region) == ""
    monkeypatch.setenv("NODE_REGION", "nepal")
    assert download_source("", Settings().region) == release_url("nepal")
