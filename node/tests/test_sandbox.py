import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fixture_pack import build_nepal_pack
from meshed_nodes import MeshedNodes

from storm_shield import sandbox as sandbox_module
from storm_shield.cache_pack import release_url
from storm_shield.community_reading import CommunityReading, Measurement, Position
from storm_shield.sandbox import HUB_SITE, SENSOR_SITES, Sandbox, SandboxError, pack_for


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    path = tmp_path / "cache-pack.zip"
    path.write_bytes(build_nepal_pack())
    return path


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where the Sandbox's temporary folder goes, so a test can see it was removed."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def test_every_sensor_is_registered_and_its_reading_is_in_the_hubs_state(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        state = TestClient(sandbox.hub).get("/api/state").json()

    assert state["sandbox"] == {"label": "SIMULATED"}
    nodes = {node["id"]: node for node in state["nodes"]}
    for site in SENSOR_SITES:
        assert nodes[site.name]["registered"] is True
        assert nodes[site.name]["simulated"] is True
        assert set(nodes[site.name]["measurements"]) == {
            "water_level",
            "rain_rate",
            "soil_moisture",
            "air_pressure",
        }


def test_the_temporary_folder_is_removed_on_exit_even_after_an_error(
    pack: Path, scratch: Path
) -> None:
    with pytest.raises(KeyboardInterrupt), Sandbox(pack):
        assert list(scratch.iterdir())
        raise KeyboardInterrupt
    assert list(scratch.iterdir()) == []


def test_a_missing_pack_says_how_to_get_it(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="no Cache Pack at"):
        Sandbox(tmp_path / "missing.zip")


def test_a_damaged_pack_is_named_and_leaves_no_folder_behind(tmp_path: Path, scratch: Path) -> None:
    damaged = tmp_path / "damaged.zip"
    damaged.write_bytes(b"not a zip")
    with (
        pytest.raises(SandboxError, match="damaged.zip is not a usable Cache Pack"),
        Sandbox(damaged),
    ):
        pass
    assert list(scratch.iterdir()) == []


def test_a_node_outside_the_sandbox_reports_no_sandbox(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start("porch")
    assert meshed_nodes["porch"].get("/api/state").json()["sandbox"] is None


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty checkout, so a test decides which packs are on disk."""
    monkeypatch.setattr(sandbox_module, "REPO", tmp_path / "repo")
    return tmp_path / "repo"


def _a_release_that_serves(requests: list[httpx.Request]) -> httpx.Client:
    def release(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"the pack")

    return httpx.Client(transport=httpx.MockTransport(release))


def test_a_pack_built_on_disk_is_used_without_downloading(repo: Path) -> None:
    built = repo / "node" / "build" / "nepal" / "cache-pack.zip"
    built.parent.mkdir(parents=True)
    built.write_bytes(b"built here")
    requests: list[httpx.Request] = []

    with _a_release_that_serves(requests) as client:
        assert pack_for("nepal", client) == built

    assert requests == []


def test_a_region_pack_is_downloaded_from_its_release_once(repo: Path) -> None:
    requests: list[httpx.Request] = []

    with _a_release_that_serves(requests) as client:
        pack = pack_for("nepal", client)
        assert pack_for("nepal", client) == pack

    assert pack.read_bytes() == b"the pack"
    assert [str(request.url) for request in requests] == [release_url("nepal")]
    assert not pack.with_name("cache-pack.zip.part").exists()


def test_cache_pack_url_wins_over_the_release(repo: Path) -> None:
    requests: list[httpx.Request] = []

    with _a_release_that_serves(requests) as client:
        pack_for("nepal", client, "http://laptop.local/cache-pack.zip")

    assert [str(request.url) for request in requests] == ["http://laptop.local/cache-pack.zip"]


def test_a_failed_download_says_so_and_how_to_build_the_pack(repo: Path) -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(offline)) as client,
        pytest.raises(SandboxError, match=r"could not download the nepal Cache Pack.*build-cache"),
    ):
        pack_for("nepal", client)
    assert not (repo / ".demo").exists()


def test_a_region_with_no_pack_anywhere_prints_the_build_command(repo: Path) -> None:
    requests: list[httpx.Request] = []

    with (
        _a_release_that_serves(requests) as client,
        pytest.raises(SandboxError, match=r"`scripts/build-cache-pack\.sh unpublished`"),
    ):
        pack_for("unpublished", client)

    assert requests == []


def _nodes(sandbox: Sandbox) -> dict[str, dict[str, Any]]:
    answer = TestClient(sandbox.hub).get("/api/sandbox/nodes").json()
    return {node["id"]: node for node in answer["nodes"]}


def _set_radio_range(sandbox: Sandbox, metres: float) -> dict[str, Any]:
    response = TestClient(sandbox.hub).post(
        "/api/sandbox/radio-range", json={"radio_range_m": metres}
    )
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def _surge_at(sandbox: Sandbox, sender: str, river_km: float) -> None:
    """Have a registered Sensor's reading jump 3.2 m in 8 s, which makes the Hub warn."""
    now = int(time.time())
    for seq, (taken_at, water_m) in enumerate([(now - 8, 0.2), (now, 3.4)], start=1_000_000):
        sandbox.network.deliver(
            sender,
            CommunityReading(
                node=sender,
                seq=seq,
                t=taken_at,
                sim=True,
                pos=Position(27.9, 85.1),
                river_km=river_km,
                m=[Measurement("water_level", water_m, "m")],
            ),
        )


def test_the_node_list_gives_each_nodes_position_links_and_hops_to_the_hub(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        # The Hub is 7.0 km from s3 and 25.9 km from s2; s1 (35.8 km) and s0 (49.3 km) are out of
        # its own reach, and both are within 30 km of s2.
        _set_radio_range(sandbox, 30_000)
        nodes = _nodes(sandbox)

    assert nodes["hub"]["role"] == "hub"
    assert nodes["hub"]["position"] == [HUB_SITE.latitude, HUB_SITE.longitude]
    assert {name: node["hops"] for name, node in nodes.items()} == {
        "hub": 0,
        "s3": 1,
        "s2": 1,
        "s1": 2,
        "s0": 2,
    }
    assert set(nodes["s2"]["links"]) == {"hub", "s0", "s1"}


def test_setting_the_radio_range_answers_with_the_new_picture(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        answer = _set_radio_range(sandbox, 10_000)

    assert answer["radio_range_m"] == 10_000
    hops = {node["id"]: node["hops"] for node in answer["nodes"]}
    assert hops == {"hub": 0, "s3": 1, "s2": None, "s1": None, "s0": None}


def test_a_range_of_nothing_is_refused(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        response = TestClient(sandbox.hub).post(
            "/api/sandbox/radio-range", json={"radio_range_m": 0}
        )

    assert response.status_code == 422


def test_a_node_with_no_path_to_the_hub_has_not_heard_the_warning(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        _set_radio_range(sandbox, 10_000)
        assert not any(node["heard_warning"] for node in _nodes(sandbox).values())

        _surge_at(sandbox, "s3", river_km=54.0)
        nodes = _nodes(sandbox)

    assert nodes["hub"]["heard_warning"] is True
    assert nodes["s3"]["heard_warning"] is True
    for cut_off in ("s2", "s1", "s0"):
        assert nodes[cut_off]["hops"] is None
        assert nodes[cut_off]["heard_warning"] is False


def _sensors(sandbox: Sandbox, method: str, path: str, **body: Any) -> httpx.Response:
    response: httpx.Response = TestClient(sandbox.hub).request(
        method, f"/api/sandbox/sensors{path}", json=body or None
    )
    return response


def _heard_by_hub(sandbox: Sandbox) -> dict[str, dict[str, Any]]:
    state = TestClient(sandbox.hub).get("/api/state").json()
    return {node["id"]: node for node in state["nodes"]}


# Beside the Hub, on the pack's river line, and about 3 km from it.
BY_THE_RIVER = {"latitude": 27.9735, "longitude": 85.1855}
UP_THE_HILL = {"latitude": 27.9735, "longitude": 85.2155}


def test_a_sensor_added_at_a_spot_is_registered_and_the_hub_hears_it_from_there(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        response = _sensors(sandbox, "POST", "", **BY_THE_RIVER)
        heard = _heard_by_hub(sandbox)

    assert response.status_code == 200
    added = {node["id"]: node for node in response.json()["nodes"]}["s4"]
    assert added["position"] == [BY_THE_RIVER["latitude"], BY_THE_RIVER["longitude"]]
    assert added["hops"] == 1
    assert heard["s4"]["registered"] is True
    assert heard["s4"]["position"] == pytest.approx(
        [BY_THE_RIVER["latitude"], BY_THE_RIVER["longitude"]], abs=0.002
    )
    assert "water_level" in heard["s4"]["measurements"]


def test_a_sensor_moved_up_the_hill_reads_from_there_at_once(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_RIVER)
        assert "water_level" in _heard_by_hub(sandbox)["s4"]["measurements"]

        response = _sensors(sandbox, "PUT", "/s4", **UP_THE_HILL)
        heard = _heard_by_hub(sandbox)["s4"]

    assert response.status_code == 200
    assert heard["position"] == pytest.approx(
        [UP_THE_HILL["latitude"], UP_THE_HILL["longitude"]], abs=0.002
    )
    # Dry ground: the Sensor still reads the weather, but no river water.
    assert "water_level" not in heard["measurements"]
    assert "rain_rate" in heard["measurements"]


def test_moving_a_sensor_into_range_makes_the_hub_hear_it(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _set_radio_range(sandbox, 10_000)
        far = _sensors(sandbox, "POST", "", latitude=28.4, longitude=85.5)
        out_of_range = {node["id"]: node for node in far.json()["nodes"]}["s4"]
        unheard = "s4" in _heard_by_hub(sandbox)

        near = _sensors(sandbox, "PUT", "/s4", **BY_THE_RIVER)
        heard = _heard_by_hub(sandbox)

    assert out_of_range["hops"] is None
    assert not unheard
    assert {node["id"]: node for node in near.json()["nodes"]}["s4"]["hops"] == 1
    assert heard["s4"]["registered"] is True


def test_a_removed_sensor_is_off_the_mesh_and_the_node_list(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_RIVER)
        response = _sensors(sandbox, "DELETE", "/s4")
        listed = _nodes(sandbox)

    assert response.status_code == 200
    assert "s4" not in {node["id"] for node in response.json()["nodes"]}
    assert set(listed) == {"hub", "s0", "s1", "s2", "s3"}
    assert all("s4" not in node["links"] for node in listed.values())


def test_a_removed_sensors_number_is_not_given_out_again(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_RIVER)
        _sensors(sandbox, "DELETE", "/s4")
        again = _sensors(sandbox, "POST", "", **BY_THE_RIVER)

    assert "s5" in {node["id"] for node in again.json()["nodes"]}


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("sensor_id", ["hub", "nobody"])
def test_the_hub_and_strangers_cannot_be_moved_or_removed(
    pack: Path, scratch: Path, method: str, sensor_id: str
) -> None:
    with Sandbox(pack) as sandbox:
        response = _sensors(
            sandbox, method, f"/{sensor_id}", **(BY_THE_RIVER if method == "PUT" else {})
        )
        listed = _nodes(sandbox)

    assert response.status_code == 404
    assert set(listed) == {"hub", "s0", "s1", "s2", "s3"}


def test_a_spot_off_the_planet_is_refused(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        response = _sensors(sandbox, "POST", "", latitude=91, longitude=0)

    assert response.status_code == 422


def test_a_sensor_the_registry_has_no_room_for_is_refused_and_not_left_behind(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        refused = None
        for _ in range(20):
            response = _sensors(sandbox, "POST", "", **BY_THE_RIVER)
            if response.status_code != 200:
                refused = response
                break
        listed = _nodes(sandbox)

    assert refused is not None
    assert refused.status_code == 409
    assert "no longer fit one packet" in refused.json()["detail"]
    # The Hub, s0 to s3, and the Sensors that did fit: the refused one is not among them.
    assert len(listed) >= 6
    assert len(listed) < 20
