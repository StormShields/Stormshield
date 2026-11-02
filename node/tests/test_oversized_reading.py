import logging
from datetime import UTC, datetime

import pytest
from meshed_nodes import a_calm_day

from storm_shield.community_reading import CommunityReading, Position, Reading
from storm_shield.mesh import InMemoryNetwork, MessageTooLarge
from storm_shield.node_registry import MAX_SIGNED_MESSAGE_BYTES, SIGNATURE_BYTES
from storm_shield.reading_publisher import ReadingPublisher

# What a Sensor with every kind the spec lists sends at realistic values (docs/specs/general-sensors.md).
ALL_EIGHT_KINDS = [
    ("water_level", 1.23, "m"),
    ("rain_rate", 12.5, "mm/h"),
    ("soil_moisture", 31.4, "%"),
    ("air_pressure", 1013.2, "hPa"),
    ("air_temperature", 27.8, "°C"),
    ("humidity", 86.0, "%"),
    ("wind_speed", 14.3, "m/s"),
    ("camera", 0.42, "score"),
]
LEFT_OF_THE_BUDGET = 350


def _readings(kinds: list[tuple[str, float, str]]) -> list[Reading]:
    now = datetime.now(UTC)
    return [Reading(kind=k, value=v, unit=u, timestamp=now) for k, v, u in kinds]


def _reading(node: str, kinds: list[tuple[str, float, str]]) -> CommunityReading:
    return CommunityReading.from_measurements(
        node=node,
        seq=1234,
        position=Position(26.640, -81.872),
        readings=_readings(kinds),
        river_km=12.5,
    )


def test_a_reading_with_all_eight_kinds_at_realistic_values_is_under_the_budget() -> None:
    reading = _reading("a1b2c3d4e5f6", ALL_EIGHT_KINDS)
    assert len(reading.model_dump_json().encode()) < LEFT_OF_THE_BUDGET


def test_the_in_memory_mesh_refuses_what_one_packet_cannot_carry() -> None:
    network = InMemoryNetwork()
    sender = network.join("porch")
    listener = network.join("listener")
    heard: list[object] = []
    listener.subscribe(lambda _sender, message: heard.append(message))
    too_many = [(f"kind_{n}", 1.0, "u") for n in range(40)]

    with pytest.raises(MessageTooLarge, match="over one Reticulum packet"):
        sender.publish(_reading("porch", too_many))

    assert heard == []


def test_the_in_memory_limit_is_the_signed_size_real_reticulum_counts() -> None:
    network = InMemoryNetwork()
    sender = network.join("porch")
    listener = network.join("listener")
    heard: list[object] = []
    listener.subscribe(lambda _sender, message: heard.append(message))
    kinds = [("water_level", 1.0, "m")]
    while True:
        bigger = [*kinds, (f"k{len(kinds)}", 1.0, "u")]
        size = len(_reading("porch", bigger).model_dump_json().encode()) + SIGNATURE_BYTES
        if size > MAX_SIGNED_MESSAGE_BYTES:
            break
        kinds = bigger

    sender.publish(_reading("porch", kinds))
    assert len(heard) == 1
    with pytest.raises(MessageTooLarge):
        sender.publish(_reading("porch", bigger))


def test_a_node_whose_reading_does_not_fit_logs_once_shares_nothing_and_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    network = InMemoryNetwork()
    listener = network.join("listener")
    heard: list[object] = []
    listener.subscribe(lambda _sender, message: heard.append(message))
    too_many = _readings([(f"kind_{n}", 1.0, "u") for n in range(40)])
    publisher = ReadingPublisher(
        network.join("porch"),
        position=lambda: Position(0, 0),
        river_km=lambda: None,
        measurements=lambda: too_many,
        keep=lambda _node, _reading: None,
    )
    steady = ReadingPublisher(
        network.join("steady"),
        position=lambda: Position(0, 0),
        river_km=lambda: None,
        measurements=a_calm_day,
        keep=lambda _node, _reading: None,
    )

    with caplog.at_level(logging.ERROR):
        publisher.share()
        publisher.share()
        steady.share()

    assert [record.levelno for record in caplog.records] == [logging.ERROR]
    assert "over one Reticulum packet" in caplog.text
    assert [m.node for m in heard if isinstance(m, CommunityReading)] == ["steady"]
