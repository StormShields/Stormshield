import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fort_myers_pack import build_fort_myers_pack
from meshed_nodes import MeshedNodes
from terrarium import ground_at

from storm_shield import sandbox as sandbox_module
from storm_shield.cache_pack import release_url
from storm_shield.community_reading import CommunityReading, Measurement, Position
from storm_shield.sandbox import HUB_SITE, SENSOR_SITES, Sandbox, SandboxError, pack_for

# On the bay shore, where the Event's water arrives first, and on a hill inland that it never reaches.
BY_THE_BAY = {"latitude": 26.4507, "longitude": -81.9533}
UP_THE_HILL = {"latitude": 26.57, "longitude": -81.75}
# Beside the Hub, so it is the only Sensor a short radio range reaches; and far past every other.
BESIDE_THE_HUB = {"latitude": 26.62, "longitude": -81.83}
FAR_AWAY = {"latitude": 27.4, "longitude": -82.2}
FIRST_ADDED = f"s{len(SENSOR_SITES)}"
SITE_NAMES = {site.name for site in SENSOR_SITES}


def _terrain() -> dict[str, bytes]:
    """The datum under the Hub and every Sensor, so the Event's water reaches them, and 10 m of
    hill at UP_THE_HILL."""
    return {
        **{
            path: tile
            for site in (HUB_SITE, *SENSOR_SITES)
            for path, tile in ground_at(site.latitude, site.longitude).items()
        },
        **ground_at(**UP_THE_HILL, metres=10),
    }


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    path = tmp_path / "cache-pack.zip"
    path.write_bytes(build_fort_myers_pack(_terrain()))
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


def _surge_at(sandbox: Sandbox, sender: str) -> None:
    """Have a registered Sensor's water jump 0.9 m in 10 minutes, past the Region's warning height,
    which makes the Hub warn."""
    now = int(time.time())
    for seq, (taken_at, water_m) in enumerate([(now - 600, 0.3), (now, 1.2)], start=1_000_000):
        sandbox.network.deliver(
            sender,
            CommunityReading(
                node=sender,
                seq=seq,
                t=taken_at,
                sim=True,
                pos=Position(26.4, -81.9),
                m=[Measurement("water_level", water_m, "m")],
            ),
        )


def test_the_node_list_gives_each_nodes_position_links_and_hops_to_the_hub(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        # Only s2 (15.2 km) is within 16 km of the Hub; s0 and s1 are within 10 km of s2, and the
        # southern sites hop on from those.
        _set_radio_range(sandbox, 16_000)
        nodes = _nodes(sandbox)

    assert nodes["hub"]["role"] == "hub"
    assert nodes["hub"]["position"] == [HUB_SITE.latitude, HUB_SITE.longitude]
    hops = {name: node["hops"] for name, node in nodes.items()}
    assert hops["hub"] == 0
    assert hops["s2"] == 1
    assert hops["s0"] == hops["s1"] == 2
    assert all(hops[name] is not None for name in SITE_NAMES)
    assert {"hub", "s0", "s1"} <= set(nodes["s2"]["links"])
    assert "s3" not in nodes["s2"]["links"]


def test_setting_the_radio_range_answers_with_the_new_picture(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        answer = _set_radio_range(sandbox, 10_000)

    assert answer["radio_range_m"] == 10_000
    hops = {node["id"]: node["hops"] for node in answer["nodes"]}
    assert hops == {"hub": 0, **{name: None for name in SITE_NAMES}}


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
        _set_radio_range(sandbox, 20_000)
        _sensors(sandbox, "POST", "", **FAR_AWAY)
        assert not any(node["heard_warning"] for node in _nodes(sandbox).values())

        _surge_at(sandbox, "s4")
        nodes = _nodes(sandbox)

    assert nodes["hub"]["heard_warning"] is True
    assert nodes["s4"]["heard_warning"] is True
    assert nodes[FIRST_ADDED]["hops"] is None
    assert nodes[FIRST_ADDED]["heard_warning"] is False


def _sensors(sandbox: Sandbox, method: str, path: str, **body: Any) -> httpx.Response:
    response: httpx.Response = TestClient(sandbox.hub).request(
        method, f"/api/sandbox/sensors{path}", json=body or None
    )
    return response


def _heard_by_hub(sandbox: Sandbox) -> dict[str, dict[str, Any]]:
    state = TestClient(sandbox.hub).get("/api/state").json()
    return {node["id"]: node for node in state["nodes"]}


def test_a_sensor_added_at_a_spot_is_registered_and_the_hub_hears_it_from_there(
    pack: Path, scratch: Path
) -> None:
    with Sandbox(pack) as sandbox:
        response = _sensors(sandbox, "POST", "", **BY_THE_BAY)
        heard = _heard_by_hub(sandbox)

    assert response.status_code == 200
    added = {node["id"]: node for node in response.json()["nodes"]}[FIRST_ADDED]
    assert added["position"] == [BY_THE_BAY["latitude"], BY_THE_BAY["longitude"]]
    assert added["hops"] == 1
    assert heard[FIRST_ADDED]["registered"] is True
    assert heard[FIRST_ADDED]["position"] == pytest.approx(
        [BY_THE_BAY["latitude"], BY_THE_BAY["longitude"]], abs=0.002
    )
    assert "water_level" in heard[FIRST_ADDED]["measurements"]


def test_a_sensor_moved_up_the_hill_reads_from_there_at_once(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_BAY)
        assert "water_level" in _heard_by_hub(sandbox)[FIRST_ADDED]["measurements"]

        response = _sensors(sandbox, "PUT", f"/{FIRST_ADDED}", **UP_THE_HILL)
        heard = _heard_by_hub(sandbox)[FIRST_ADDED]

    assert response.status_code == 200
    assert heard["position"] == pytest.approx(
        [UP_THE_HILL["latitude"], UP_THE_HILL["longitude"]], abs=0.002
    )
    # Dry ground: the Sensor still reads the weather, but no water.
    assert "water_level" not in heard["measurements"]
    assert "rain_rate" in heard["measurements"]


def test_moving_a_sensor_into_range_makes_the_hub_hear_it(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _set_radio_range(sandbox, 10_000)
        far = _sensors(sandbox, "POST", "", **FAR_AWAY)
        out_of_range = {node["id"]: node for node in far.json()["nodes"]}[FIRST_ADDED]
        unheard = FIRST_ADDED in _heard_by_hub(sandbox)

        near = _sensors(sandbox, "PUT", f"/{FIRST_ADDED}", **BESIDE_THE_HUB)
        heard = _heard_by_hub(sandbox)

    assert out_of_range["hops"] is None
    assert not unheard
    assert {node["id"]: node for node in near.json()["nodes"]}[FIRST_ADDED]["hops"] == 1
    assert heard[FIRST_ADDED]["registered"] is True


def test_a_removed_sensor_is_off_the_mesh_and_the_node_list(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_BAY)
        response = _sensors(sandbox, "DELETE", f"/{FIRST_ADDED}")
        listed = _nodes(sandbox)

    assert response.status_code == 200
    assert FIRST_ADDED not in {node["id"] for node in response.json()["nodes"]}
    assert set(listed) == {"hub", *SITE_NAMES}
    assert all(FIRST_ADDED not in node["links"] for node in listed.values())


def test_a_removed_sensors_number_is_not_given_out_again(pack: Path, scratch: Path) -> None:
    with Sandbox(pack) as sandbox:
        _sensors(sandbox, "POST", "", **BY_THE_BAY)
        _sensors(sandbox, "DELETE", f"/{FIRST_ADDED}")
        again = _sensors(sandbox, "POST", "", **BY_THE_BAY)

    assert f"s{len(SENSOR_SITES) + 1}" in {node["id"] for node in again.json()["nodes"]}


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("sensor_id", ["hub", "nobody"])
def test_the_hub_and_strangers_cannot_be_moved_or_removed(
    pack: Path, scratch: Path, method: str, sensor_id: str
) -> None:
    with Sandbox(pack) as sandbox:
        response = _sensors(
            sandbox, method, f"/{sensor_id}", **(BY_THE_BAY if method == "PUT" else {})
        )
        listed = _nodes(sandbox)

    assert response.status_code == 404
    assert set(listed) == {"hub", *SITE_NAMES}


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
            response = _sensors(sandbox, "POST", "", **BY_THE_BAY)
            if response.status_code != 200:
                refused = response
                break
        listed = _nodes(sandbox)

    assert refused is not None
    assert refused.status_code == 409
    assert "no longer fit one packet" in refused.json()["detail"]
    # The Hub, the Region's Sensors and the ones that did fit: the refused one is not among them.
    assert len(listed) > 1 + len(SENSOR_SITES)
    assert len(listed) < 20
