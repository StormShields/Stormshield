import stat
from pathlib import Path

import pytest
import RNS

from storm_shield.community_reading import CommunityReading, Measurement, Position
from storm_shield.community_warning import CommunityWarning
from storm_shield.node_registry import (
    MAX_SIGNED_MESSAGE_BYTES,
    NodeRegistryMessage,
    RegisteredNode,
    SignUp,
)
from storm_shield.replay import ReplayClockMessage
from storm_shield.reticulum_mesh import (
    SIGNATURE_LENGTH,
    load_or_create_identity,
    node_id,
    sign,
    verify,
)
from storm_shield.shelter_status import ShelterStatus


def _reading(node: str) -> CommunityReading:
    return CommunityReading(
        node=node,
        seq=1_760_650_928,
        t=1_760_650_928,
        sim=True,
        pos=Position(29.652, -82.324),
        m=[
            Measurement("air_pressure", 991.2, "hPa"),
            Measurement("water_level", 0.84, "m"),
            Measurement("rain_rate", 14.8, "mm/h"),
            Measurement("soil_moisture", 91, "%"),
        ],
    )


def test_a_reading_from_an_announced_node_verifies() -> None:
    porch = RNS.Identity()
    reading = _reading(node_id(porch))
    assert verify(sign(porch, reading), {node_id(porch): porch}) == (node_id(porch), reading)


def test_a_reading_from_a_node_not_yet_announced_is_dropped() -> None:
    porch = RNS.Identity()
    assert verify(sign(porch, _reading(node_id(porch))), {}) is None


def test_a_reading_signed_by_someone_else_is_dropped() -> None:
    porch, intruder = RNS.Identity(), RNS.Identity()
    claims_to_be_porch = sign(intruder, _reading(node_id(porch)))
    assert verify(claims_to_be_porch, {node_id(porch): porch}) is None


def test_a_reading_changed_in_transit_is_dropped() -> None:
    porch = RNS.Identity()
    packet = bytearray(sign(porch, _reading(node_id(porch))))
    packet[-3] ^= 1
    assert verify(bytes(packet), {node_id(porch): porch}) is None


def test_garbage_is_dropped() -> None:
    assert verify(b"", {}) is None
    assert verify(b"x" * (SIGNATURE_LENGTH + 5), {}) is None


def test_a_signed_reading_fits_one_unencrypted_packet() -> None:
    porch = RNS.Identity()
    assert len(sign(porch, _reading(node_id(porch)))) <= RNS.Packet.PLAIN_MDU


def _shelters(ver: int = 3) -> ShelterStatus:
    return ShelterStatus(ver=ver, t=1_760_650_928, open=["sr-center", "hs-gym"])


def test_shelter_status_signed_by_the_hub_verifies_as_from_the_hub() -> None:
    hub = RNS.Identity()
    known = {node_id(hub): hub}
    assert verify(sign(hub, _shelters()), known, node_id(hub)) == (node_id(hub), _shelters())


def test_shelter_status_signed_by_another_node_is_dropped() -> None:
    hub, rogue = RNS.Identity(), RNS.Identity()
    known = {node_id(hub): hub, node_id(rogue): rogue}
    assert verify(sign(rogue, _shelters()), known, node_id(hub)) is None


def test_shelter_status_is_dropped_when_no_hub_is_configured() -> None:
    hub = RNS.Identity()
    assert verify(sign(hub, _shelters()), {node_id(hub): hub}) is None


def test_shelter_status_is_dropped_before_the_hub_has_announced() -> None:
    hub = RNS.Identity()
    assert verify(sign(hub, _shelters()), {}, node_id(hub)) is None


def test_a_message_kind_this_node_does_not_know_is_ignored() -> None:
    hub = RNS.Identity()
    body = b'{"v": 1, "kind": "from-the-future", "t": 1}'
    packet = bytes(hub.sign(body)) + body
    assert verify(packet, {node_id(hub): hub}, node_id(hub)) is None


def _signed_by_hub(hub: RNS.Identity, body: bytes) -> bytes:
    return bytes(hub.sign(body)) + body


def test_a_signed_message_of_an_unknown_format_version_is_ignored() -> None:
    hub = RNS.Identity()
    body = b'{"v": 2, "kind": "shelters", "ver": 1, "t": 1, "open": []}'
    assert verify(_signed_by_hub(hub, body), {node_id(hub): hub}, node_id(hub)) is None


def test_a_signed_message_with_extra_fields_is_accepted_and_the_extras_ignored() -> None:
    hub = RNS.Identity()
    body = b'{"v": 1, "kind": "shelters", "ver": 1, "t": 1, "open": [], "newer": {"a": 1}}'
    expected = (node_id(hub), ShelterStatus(ver=1, t=1, open=[]))
    assert verify(_signed_by_hub(hub, body), {node_id(hub): hub}, node_id(hub)) == expected


def test_a_signed_message_that_is_not_json_is_ignored() -> None:
    hub = RNS.Identity()
    assert verify(_signed_by_hub(hub, b"{nope"), {node_id(hub): hub}, node_id(hub)) is None


def test_a_signed_shelter_status_fits_one_unencrypted_packet() -> None:
    hub = RNS.Identity()
    twelve = ShelterStatus(ver=3, t=1_760_650_928, open=[f"shelter-{n:02}" for n in range(12)])
    assert len(sign(hub, twelve)) <= RNS.Packet.PLAIN_MDU


def test_the_event_clock_signed_by_the_hub_verifies_and_one_signed_by_another_node_is_dropped() -> (
    None
):
    hub, rogue = RNS.Identity(), RNS.Identity()
    known = {node_id(hub): hub, node_id(rogue): rogue}
    clock = ReplayClockMessage(
        event="bhote-koshi-2026", state="playing", event_t=1_787_712_300, rate=30
    )
    assert verify(sign(hub, clock), known, node_id(hub)) == (node_id(hub), clock)
    assert verify(sign(rogue, clock), known, node_id(hub)) is None
    assert len(sign(hub, clock)) <= RNS.Packet.PLAIN_MDU


def test_a_community_warning_signed_by_the_hub_verifies_and_one_signed_by_another_node_is_dropped() -> (
    None
):
    hub, rogue = RNS.Identity(), RNS.Identity()
    known = {node_id(hub): hub, node_id(rogue): rogue}
    warning = CommunityWarning(
        id=1_787_716_020,
        t=1_787_716_021,
        hazard="flash_flood",
        nodes=["b7e1f40a92c5"],
        reasons=["water_surge"],
        origin="b7e1f40a92c5",
        origin_km=-12.2,
        surge_t=1_787_716_020,
    )
    assert verify(sign(hub, warning), known, node_id(hub)) == (node_id(hub), warning)
    assert verify(sign(rogue, warning), known, node_id(hub)) is None
    assert len(sign(hub, warning)) <= RNS.Packet.PLAIN_MDU


def test_a_node_keeps_its_identity_in_a_file_only_its_owner_can_read(tmp_path: Path) -> None:
    path = tmp_path / "identity"
    first = load_or_create_identity(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert node_id(load_or_create_identity(path)) == node_id(first)


def test_an_identity_file_readable_by_everyone_is_locked_down_on_load(tmp_path: Path) -> None:
    path = tmp_path / "identity"
    load_or_create_identity(path)
    path.chmod(0o644)
    load_or_create_identity(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_damaged_identity_file_stops_the_node_and_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "identity"
    path.write_bytes(b"cut short")
    with pytest.raises(ValueError, match="identity.*Delete it"):
        load_or_create_identity(path)


def test_a_sign_up_verifies_against_the_node_it_names_and_a_forged_one_is_dropped() -> None:
    porch, intruder, hub = RNS.Identity(), RNS.Identity(), RNS.Identity()
    known = {node_id(porch): porch, node_id(intruder): intruder, node_id(hub): hub}
    sign_up = SignUp(node=node_id(porch), name="garage")
    assert verify(sign(porch, sign_up), known, node_id(hub)) == (node_id(porch), sign_up)
    assert verify(sign(intruder, sign_up), known, node_id(hub)) is None


def test_a_sign_up_from_a_node_that_has_not_announced_is_dropped() -> None:
    porch, hub = RNS.Identity(), RNS.Identity()
    sign_up = SignUp(node=node_id(porch), name="garage")
    assert verify(sign(porch, sign_up), {node_id(hub): hub}, node_id(hub)) is None


def test_a_registry_signed_by_anyone_but_the_hub_is_dropped() -> None:
    hub, rogue = RNS.Identity(), RNS.Identity()
    known = {node_id(hub): hub, node_id(rogue): rogue}
    registry = NodeRegistryMessage(
        ver=4, t=1_760_650_928, nodes=[RegisteredNode(id=node_id(rogue), name="rogue")]
    )
    assert verify(sign(hub, registry), known, node_id(hub)) == (node_id(hub), registry)
    assert verify(sign(rogue, registry), known, node_id(hub)) is None


def test_the_largest_registry_the_hub_accepts_fits_one_unencrypted_packet() -> None:
    assert MAX_SIGNED_MESSAGE_BYTES == RNS.Packet.PLAIN_MDU
    hub = RNS.Identity()
    nodes = [RegisteredNode(id=f"{n:012x}", name="x" * 8) for n in range(8)]
    full = NodeRegistryMessage(ver=4, t=1_760_650_928, nodes=nodes)
    assert len(sign(hub, full)) <= RNS.Packet.PLAIN_MDU
