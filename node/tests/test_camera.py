import time
from collections.abc import Callable
from typing import Any

import pytest
from meshed_nodes import MeshedNodes

from storm_shield.camera import draw_picture
from storm_shield.community_reading import Measurement

pytestmark = pytest.mark.usefixtures("nepal_region")

WITH_CAMERA = "water_level,rain_rate,camera"


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def _heard(meshed_nodes: MeshedNodes, node: str) -> dict[str, Any]:
    nodes = meshed_nodes["hub"].get("/api/state").json()["nodes"]
    return next((n["measurements"] for n in nodes if n["id"] == node), {})


def test_a_camera_numbers_its_pictures_and_serves_the_newest(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("cam", measures=WITH_CAMERA, river_km=3.4)

    _wait_until(lambda: _heard(meshed_nodes, "cam").get("camera", {}).get("value", 0) >= 3)

    camera = _heard(meshed_nodes, "cam")["camera"]
    assert camera["unit"] == "pic"
    picture = meshed_nodes["cam"].get("/api/camera/picture")
    assert picture.status_code == 200
    assert picture.headers["content-type"].startswith("image/svg+xml")
    assert "SIMULATED" in picture.text


def test_a_node_that_does_not_declare_camera_has_no_picture_and_sends_none(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start_sensor("plain", river_km=3.4)

    _wait_until(lambda: "rain_rate" in _heard(meshed_nodes, "plain"))

    assert "camera" not in _heard(meshed_nodes, "plain")
    assert meshed_nodes["plain"].get("/api/camera/picture").status_code == 404


def test_pictures_differ_between_a_wet_and_a_dry_spot() -> None:
    wet, dry = draw_picture(2.5), draw_picture(None)

    assert wet != dry
    assert "SIMULATED" in wet and "SIMULATED" in dry


def test_a_node_in_the_water_draws_a_wet_picture_and_a_dry_node_a_dry_one(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_sensor("wet", measures=WITH_CAMERA, river_km=3.4, publish_every_seconds=60)
    meshed_nodes.start_sensor("dry", measures=WITH_CAMERA, publish_every_seconds=60)
    for name in ("wet", "dry"):
        meshed_nodes[name].app.state.share_reading()  # type: ignore[attr-defined]

    wet = meshed_nodes["wet"].get("/api/camera/picture").text
    dry = meshed_nodes["dry"].get("/api/camera/picture").text
    assert wet != dry
    assert "DRY" in dry
    assert "DRY" not in wet


def test_a_picture_holds_no_coordinates_or_node_id(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_sensor(
        "porch-cam",
        measures=WITH_CAMERA,
        river_km=3.4,
        latitude=27.91234,
        longitude=85.65432,
        publish_every_seconds=60,
    )
    meshed_nodes["porch-cam"].app.state.share_reading()  # type: ignore[attr-defined]

    picture = meshed_nodes["porch-cam"].get("/api/camera/picture").text
    assert "27.9" not in picture and "85.6" not in picture
    assert "porch" not in picture
    assert "<script" not in picture


def test_the_only_camera_data_on_the_mesh_is_the_measurement(meshed_nodes: MeshedNodes) -> None:
    heard = meshed_nodes.record_readings()
    meshed_nodes.start_sensor("cam", measures=WITH_CAMERA, river_km=3.4, publish_every_seconds=60)
    for _ in range(3):
        meshed_nodes["cam"].app.state.share_reading()  # type: ignore[attr-defined]

    _wait_until(lambda: len(heard) >= 3)

    assert [r.seq for r in heard] == sorted(r.seq for r in heard)
    cameras = [[m for m in r.m if m.kind == "camera"] for r in heard]
    assert [c[0].value for c in cameras] == list(range(1, len(cameras) + 1))
    assert all(c[0].unit == "pic" for c in cameras)
    assert all("svg" not in r.model_dump_json().lower() for r in heard)


def test_a_live_hub_hides_a_simulated_camera(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    for node in ("cam", "real"):
        meshed_nodes.announce_sign_up(node, node)
        meshed_nodes["hub"].post("/api/registry/accept", json={"id": node})
    meshed_nodes.hear_from("cam", also=[Measurement("camera", 1, "pic")])
    meshed_nodes.hear_from("real", simulated=False)

    nodes = meshed_nodes["hub"].get("/api/state").json()["nodes"]
    assert [n["id"] for n in nodes if n["id"] != "hub"] == ["real"]
