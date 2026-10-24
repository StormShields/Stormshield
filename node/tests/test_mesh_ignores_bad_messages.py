import logging
from pathlib import Path

import pytest
from fixture_pack import SHELTERS, build_nepal_pack
from meshed_nodes import MeshedNodes

from storm_shield.community_reading import CommunityReading, Measurement, Position
from storm_shield.mesh import Message, decode_message, deliver_to_listeners
from storm_shield.shelter_status import ShelterStatus

OPEN_SHELTER = str(SHELTERS[0]["id"])
STATUS = f'"kind": "shelters", "ver": 1, "t": 1760650928, "open": ["{OPEN_SHELTER}"]'


def _open(meshed_nodes: MeshedNodes, name: str) -> list[str]:
    return list(meshed_nodes[name].get("/api/shelters").json()["open"])


def _start(meshed_nodes: MeshedNodes, tmp_path: Path) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack()))


def test_a_message_of_an_unknown_kind_is_dropped_without_a_log(
    meshed_nodes: MeshedNodes, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.send_bytes(b'{"v": 1, "kind": "from-the-future", "t": 1}')
    assert caplog.records == []
    assert _open(meshed_nodes, "porch") == []


def test_a_message_with_extra_fields_is_accepted_and_the_extras_ignored(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.send_bytes(f'{{"v": 1, {STATUS}, "from_a_newer_node": [1, 2]}}'.encode())
    assert _open(meshed_nodes, "porch") == [OPEN_SHELTER]


def test_a_message_of_an_unknown_format_version_is_dropped_like_an_unknown_kind(
    meshed_nodes: MeshedNodes, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.send_bytes(f'{{"v": 2, {STATUS}}}'.encode())
    assert caplog.records == []
    assert _open(meshed_nodes, "porch") == []


@pytest.mark.parametrize(
    "garbage",
    [
        b"",
        b"not json",
        b"[1, 2]",
        b"null",
        b'{"v": 1, "kind": "shelters", "ver": "three"}',
        b'{"v": 1}',
        b'{"v": 1, "kind": ["shelters"]}',
        b'{"v": 1, "kind": {"a": 1}}',
        f"{{{STATUS}}}".encode(),
        f'{{"v": "1", {STATUS}}}'.encode(),
        f'{{"v": true, {STATUS}}}'.encode(),
    ],
)
def test_a_message_that_does_not_parse_is_logged_and_later_messages_still_arrive(
    meshed_nodes: MeshedNodes, tmp_path: Path, caplog: pytest.LogCaptureFixture, garbage: bytes
) -> None:
    _start(meshed_nodes, tmp_path)
    with caplog.at_level(logging.WARNING):
        meshed_nodes.send_bytes(garbage)
    assert "not a message this Node understands" in caplog.text
    meshed_nodes.send_bytes(f'{{"v": 1, {STATUS}}}'.encode())
    assert _open(meshed_nodes, "porch") == [OPEN_SHELTER]


def test_a_listener_that_raises_does_not_stop_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    heard: list[str] = []

    def failing(_sender: str, _message: Message) -> None:
        raise RuntimeError("bug in one listener")

    deliver_to_listeners(
        [failing, lambda sender, _: heard.append(sender)], "hub", ShelterStatus(ver=1, t=1, open=[])
    )
    assert heard == ["hub"]
    assert "a listener failed on a shelters from hub" in caplog.text


def test_a_node_whose_listener_raises_does_not_stop_the_nodes_after_it(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    meshed_nodes.join_with_failing_listener("faulty")
    meshed_nodes.start("garage", cache_pack=(tmp_path, build_nepal_pack()))
    meshed_nodes.announce_shelters(1, [OPEN_SHELTER])
    assert _open(meshed_nodes, "garage") == [OPEN_SHELTER]


def test_decoding_drops_an_unknown_kind_or_version_and_ignores_extra_fields() -> None:
    reading = CommunityReading(
        node="porch",
        seq=1,
        t=1,
        sim=True,
        pos=Position(29.652, -82.324),
        m=[
            Measurement("air_pressure", 1015, "hPa"),
            Measurement("water_level", 0.2, "m"),
            Measurement("rain_rate", 0, "mm/h"),
            Measurement("soil_moisture", 30, "%"),
        ],
    )
    with_extra = reading.model_dump_json()[:-1] + ', "extra": true}'
    assert decode_message(with_extra.encode()) == reading
    assert decode_message(b'{"v": 9, "kind": "reading"}') is None
    assert decode_message(b'{"v": 1, "kind": "tomorrow"}') is None
