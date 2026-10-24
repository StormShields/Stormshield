import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fixture_pack import SHELTERS, build_nepal_pack
from meshed_nodes import MeshedNodes

GYM = str(SHELTERS[0]["id"])
LIBRARY = "test-library"
TWO_SHELTERS = [*SHELTERS, {**SHELTERS[0], "id": LIBRARY, "name": "Test Library"}]
REPEAT_SECONDS = 0.02


def _open(meshed_nodes: MeshedNodes, name: str) -> list[str]:
    return list(meshed_nodes[name].get("/api/shelters").json()["open"])


def _set_open(meshed_nodes: MeshedNodes, shelter_id: str, is_open: bool) -> None:
    meshed_nodes["hub"].post("/api/shelters/open", json={"id": shelter_id, "open": is_open})


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


def _start_hub(
    meshed_nodes: MeshedNodes, tmp_path: Path, shelters: list[dict[str, object]]
) -> None:
    meshed_nodes.start_hub(
        (tmp_path, build_nepal_pack(shelters=shelters)), shelter_repeat_seconds=REPEAT_SECONDS
    )


def test_a_restarted_hub_keeps_a_closed_shelter_closed_on_every_node(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    pack = build_nepal_pack(shelters=TWO_SHELTERS)
    meshed_nodes.start("porch", "garage", cache_pack=(tmp_path, pack))
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)
    _set_open(meshed_nodes, GYM, False)

    meshed_nodes.stop_hub()
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)

    assert _open(meshed_nodes, "hub") == [LIBRARY]
    for name in ("porch", "garage"):
        assert _open(meshed_nodes, name) == [LIBRARY]


def test_a_shelter_missing_from_the_pack_after_a_restart_is_dropped(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS)))
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)

    meshed_nodes.stop_hub()
    _start_hub(meshed_nodes, tmp_path, SHELTERS)

    assert _open(meshed_nodes, "hub") == [GYM]
    # Only a `ver` higher than the pre-restart one replaces what the Node holds.
    _wait_until(lambda: _open(meshed_nodes, "porch") == [GYM])


def test_a_restart_does_not_reseed_a_shelter_that_stayed_open(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)
    _set_open(meshed_nodes, LIBRARY, False)
    _set_open(meshed_nodes, LIBRARY, True)

    meshed_nodes.stop_hub()
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)

    assert _open(meshed_nodes, "hub") == [GYM, LIBRARY]


def test_the_first_announcement_after_a_restart_has_a_higher_ver(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    heard = meshed_nodes.record_shelter_status()
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)
    _set_open(meshed_nodes, GYM, False)
    ver_before_restart = max(status.ver for status in heard)

    meshed_nodes.stop_hub()
    heard.clear()
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)

    assert heard[0].ver > ver_before_restart
    assert heard[0].open == [LIBRARY]


def test_a_state_file_that_cannot_be_read_stops_the_hub_and_names_the_file(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    state_file = tmp_path / "hub" / "data" / "shelter_status.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text('{"ver": 3')

    with pytest.raises(RuntimeError, match="shelter_status.json"):
        _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)


def test_a_change_that_cannot_be_saved_is_not_announced(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack(shelters=TWO_SHELTERS)))
    _start_hub(meshed_nodes, tmp_path, TWO_SHELTERS)
    # A directory where the temporary file belongs makes every save fail.
    (tmp_path / "hub" / "data" / "shelter_status.tmp").mkdir()

    with pytest.raises(OSError):
        _set_open(meshed_nodes, GYM, False)

    assert _open(meshed_nodes, "hub") == [GYM, LIBRARY]
    assert _open(meshed_nodes, "porch") == [GYM, LIBRARY]
