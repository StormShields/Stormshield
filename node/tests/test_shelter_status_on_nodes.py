from pathlib import Path

from fixture_pack import SHELTERS, build_nepal_pack
from meshed_nodes import MeshedNodes

OPEN_SHELTER = str(SHELTERS[0]["id"])


def _start(meshed_nodes: MeshedNodes, tmp_path: Path, *names: str) -> None:
    meshed_nodes.start(*names, cache_pack=(tmp_path, build_nepal_pack()))


def _open(meshed_nodes: MeshedNodes, name: str) -> list[str]:
    return list(meshed_nodes[name].get("/api/shelters").json()["open"])


def test_nothing_is_open_before_the_hub_announces(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    assert _open(meshed_nodes, "porch") == []


def test_an_announced_shelter_shows_on_every_node(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch", "garage")
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER])
    assert _open(meshed_nodes, "porch") == [OPEN_SHELTER]
    assert _open(meshed_nodes, "garage") == [OPEN_SHELTER]


def test_a_shelter_missing_from_a_newer_announcement_reads_as_closed(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER])
    meshed_nodes.announce_shelters(2, [])
    assert _open(meshed_nodes, "porch") == []


def test_an_old_or_equal_version_does_not_undo_a_closure(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(5, [])
    meshed_nodes.announce_shelters(4, [OPEN_SHELTER])
    meshed_nodes.announce_shelters(5, [OPEN_SHELTER])
    assert _open(meshed_nodes, "porch") == []


def test_an_id_the_cache_pack_does_not_know_is_ignored(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(1, ["no-such-shelter", OPEN_SHELTER])
    assert _open(meshed_nodes, "porch") == [OPEN_SHELTER]


def test_an_announcement_from_anyone_but_the_hub_is_ignored(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER], sender="rogue")
    assert _open(meshed_nodes, "porch") == []


def test_a_node_keeps_the_last_announcement_when_the_hub_goes_quiet(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER])
    meshed_nodes.advance(3600)
    assert _open(meshed_nodes, "porch") == [OPEN_SHELTER]


def test_a_restarted_node_starts_with_no_open_shelter(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, "porch")
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER])
    meshed_nodes.remove("porch")
    _start(meshed_nodes, tmp_path, "porch")
    assert _open(meshed_nodes, "porch") == []
