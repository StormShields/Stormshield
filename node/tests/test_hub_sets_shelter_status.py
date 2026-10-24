import time
from collections.abc import Callable
from pathlib import Path

from fixture_pack import SHELTERS, build_nepal_pack
from httpx import Response
from meshed_nodes import MeshedNodes

GYM = str(SHELTERS[0]["id"])
LIBRARY = "test-library"
TWO_SHELTERS = [*SHELTERS, {**SHELTERS[0], "id": LIBRARY, "name": "Test Library"}]


def _start_hub(meshed_nodes: MeshedNodes, tmp_path: Path, **options: float) -> None:
    pack = build_nepal_pack(shelters=TWO_SHELTERS)
    meshed_nodes.start_hub((tmp_path, pack), **options)


def _open(meshed_nodes: MeshedNodes, name: str) -> list[str]:
    return list(meshed_nodes[name].get("/api/shelters").json()["open"])


def _set(meshed_nodes: MeshedNodes, shelter_id: str, is_open: bool) -> Response:
    response: Response = meshed_nodes["hub"].post(
        "/api/shelters/open", json={"id": shelter_id, "open": is_open}
    )
    return response


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def test_a_hub_with_a_pack_starts_with_every_shelter_open(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS)))
    _start_hub(meshed_nodes, tmp_path)
    assert _open(meshed_nodes, "hub") == [GYM, LIBRARY]
    assert _open(meshed_nodes, "porch") == [GYM, LIBRARY]


def test_closing_a_shelter_on_the_hub_drops_it_everywhere(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.start(
        "porch", "garage", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS))
    )
    _start_hub(meshed_nodes, tmp_path)
    response = _set(meshed_nodes, GYM, False)
    assert response.status_code == 200
    assert response.json() == {"open": [LIBRARY]}
    for name in ("hub", "porch", "garage"):
        assert _open(meshed_nodes, name) == [LIBRARY]


def test_a_closed_shelter_can_be_opened_again(meshed_nodes: MeshedNodes, tmp_path: Path) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS)))
    _start_hub(meshed_nodes, tmp_path)
    _set(meshed_nodes, GYM, False)
    _set(meshed_nodes, GYM, True)
    assert _open(meshed_nodes, "porch") == [GYM, LIBRARY]


def test_an_unknown_shelter_is_refused_with_422(meshed_nodes: MeshedNodes, tmp_path: Path) -> None:
    _start_hub(meshed_nodes, tmp_path)
    assert _set(meshed_nodes, "no-such-shelter", False).status_code == 422
    assert _open(meshed_nodes, "hub") == [GYM, LIBRARY]


def test_a_hub_without_a_pack_refuses_changes(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub()
    response = _set(meshed_nodes, GYM, False)
    assert response.status_code == 503
    assert "Cache Pack" in response.json()["detail"]


def test_a_sensor_has_no_such_route(meshed_nodes: MeshedNodes, tmp_path: Path) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack()))
    response = meshed_nodes["porch"].post("/api/shelters/open", json={"id": GYM, "open": False})
    assert response.status_code == 404


def test_a_node_that_joins_late_converges_after_a_repeat(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start_hub(meshed_nodes, tmp_path, shelter_repeat_seconds=0.02)
    _set(meshed_nodes, GYM, False)
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS)))
    _wait_until(lambda: _open(meshed_nodes, "porch") == [LIBRARY])
