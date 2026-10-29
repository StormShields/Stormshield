import json
import logging
import math
import threading
from collections.abc import Callable, Iterable
from typing import Annotated, Any, NamedTuple, Protocol, get_args

from pydantic import Field, TypeAdapter, ValidationError

from storm_shield.community_reading import CommunityReading, Position
from storm_shield.community_warning import CommunityWarning
from storm_shield.node_registry import NodeRegistryMessage, SignUp
from storm_shield.official_alert import OfficialAlert
from storm_shield.official_gauge import OfficialGaugeLevel
from storm_shield.replay import ReplayClockMessage
from storm_shield.shelter_status import ShelterStatus

Message = (
    CommunityReading
    | SignUp
    | NodeRegistryMessage
    | ShelterStatus
    | ReplayClockMessage
    | OfficialAlert
    | OfficialGaugeLevel
    | CommunityWarning
)

# The sender is whatever the Mesh verified, never something the message claims about itself.
MessageListener = Callable[[str, Message], None]

logger = logging.getLogger(__name__)

DEFAULT_RADIO_RANGE_M = 1000.0
EARTH_RADIUS_M = 6_371_000
# Where a Node joins unless told, so a caller that never places Nodes still hears everyone in range.
ORIGIN = Position(0, 0)

_MESSAGE: TypeAdapter[Message] = TypeAdapter(Annotated[Message, Field(discriminator="kind")])
# The `v` each message class declares; decode_message checks it before the classes see the body.
_FORMAT_VERSIONS: dict[str, int] = {
    message_type.model_fields["kind"].default: message_type.model_fields["v"].default
    for message_type in get_args(Message)
}


def decode_message(body: bytes) -> Message | None:
    """The message in `body`, or None if this Node cannot use it.

    A kind or format version this Node does not know is a newer Node talking, so it is dropped
    quietly; anything else that does not parse is logged. Extra fields are ignored.
    """
    fields = _fields_with_kind_and_version(body)
    if fields is not None and _FORMAT_VERSIONS.get(fields["kind"]) != fields["v"]:
        return None
    try:
        return _MESSAGE.validate_python(fields)
    except ValidationError:
        logger.warning("dropped a mesh packet that is not a message this Node understands")
        return None


def _fields_with_kind_and_version(body: bytes) -> dict[str, Any] | None:
    """The JSON object in `body` if its `kind` is a string and its `v` an integer, else None.

    Only such a message can be a newer Node's; anything else is a broken sender, and the None it
    gets here fails validation so that it is logged.
    """
    try:
        fields = json.loads(body)
    except ValueError:
        return None
    # bool is an int in Python, so `true` must not pass for version 1.
    if (
        not isinstance(fields, dict)
        or not isinstance(fields.get("kind"), str)
        or type(fields.get("v")) is not int
    ):
        return None
    return fields


def deliver_to_listeners(
    listeners: Iterable[MessageListener], sender: str, message: Message
) -> None:
    """Every listener hears the message even if one of them raises."""
    for listener in listeners:
        try:
            listener(sender, message)
        except Exception:
            # Reticulum would swallow this silently on its own thread.
            logger.exception("a listener failed on a %s from %s", message.kind, sender)


class Mesh(Protocol):
    identity: str

    def publish(self, message: Message) -> None: ...

    def subscribe(self, listener: MessageListener) -> None: ...


def metres_between(a: Position, b: Position) -> float:
    lat_a, lat_b = math.radians(a.latitude), math.radians(b.latitude)
    half_chord = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a)
        * math.cos(lat_b)
        * math.sin(math.radians(b.longitude - a.longitude) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(half_chord))


class NodeLinks(NamedTuple):
    position: Position
    # The Nodes within radio range of this one, whatever they can reach beyond.
    in_range: list[str]
    # Radio hops from the Hub to this Node, or None when no chain of Nodes joins them.
    hops_from_hub: int | None


class InMemoryNetwork:
    """Stands in for the radio: Nodes created here hear each other inside one process.

    A model of who hears whom, not of a radio: a message reaches every Node joined to its sender
    by a chain of Nodes each within `radio_range_m` of the next, instantly and without loss.
    `radio_range_m` of None is unlimited, so every Node hears every other.
    """

    def __init__(self, radio_range_m: float | None = DEFAULT_RADIO_RANGE_M) -> None:
        self._lock = threading.Lock()
        self._meshes: dict[str, InMemoryMesh] = {}
        self._positions: dict[str, Position] = {}
        self._radio_range_m = radio_range_m

    def join(
        self, identity: str, hub_identity: str = "", position: Position = ORIGIN
    ) -> "InMemoryMesh":
        mesh = InMemoryMesh(identity, self, hub_identity)
        with self._lock:
            if identity in self._meshes:
                raise ValueError(f"a Node named {identity} has already joined")
            self._meshes[identity] = mesh
            self._positions[identity] = position
        return mesh

    def leave(self, identity: str) -> None:
        with self._lock:
            self._meshes.pop(identity, None)
            self._positions.pop(identity, None)

    def move(self, identity: str, position: Position) -> None:
        """Takes effect on the next message."""
        with self._lock:
            if identity not in self._meshes:
                raise ValueError(f"no Node named {identity} has joined")
            self._positions[identity] = position

    @property
    def radio_range_m(self) -> float | None:
        with self._lock:
            return self._radio_range_m

    def set_radio_range(self, radio_range_m: float | None) -> None:
        """Takes effect on the next message; None is unlimited."""
        with self._lock:
            self._radio_range_m = radio_range_m

    def links(self, hub: str) -> dict[str, NodeLinks]:
        """Where every Node is, who is in range of it, and how many hops it is from `hub`."""
        with self._lock:
            in_range = {
                name: [
                    other
                    for other, there in self._positions.items()
                    if other != name and self._in_range(here, there)
                ]
                for name, here in self._positions.items()
            }
            hops = {hub: 0} if hub in self._positions else {}
            frontier = list(hops)
            while frontier:
                next_frontier = []
                for relay in frontier:
                    for neighbour in in_range[relay]:
                        if neighbour not in hops:
                            hops[neighbour] = hops[relay] + 1
                            next_frontier.append(neighbour)
                frontier = next_frontier
            return {
                name: NodeLinks(self._positions[name], in_range[name], hops.get(name))
                for name in self._positions
            }

    def has_joined(self, mesh: "InMemoryMesh") -> bool:
        with self._lock:
            return self._meshes.get(mesh.identity) is mesh

    def deliver(self, sender: str, message: Message) -> None:
        self.deliver_bytes(sender, message.model_dump_json().encode())

    def deliver_bytes(self, sender: str, body: bytes) -> None:
        """What the radio does: every Node the sender reaches decodes the same bytes, or drops them."""
        with self._lock:
            receivers = [self._meshes[name] for name in self._reached_from(sender)]
        wire_copy = decode_message(body)
        if wire_copy is None:
            return
        for mesh in receivers:
            mesh.receive(sender, wire_copy)

    def _reached_from(self, sender: str) -> list[str]:
        """The other Nodes the sender's message gets to, hopping through relays. Hold the lock."""
        if sender not in self._positions:
            return []
        reached = {sender}
        frontier = [sender]
        while frontier:
            relay = frontier.pop()
            for name, position in self._positions.items():
                if name not in reached and self._in_range(self._positions[relay], position):
                    reached.add(name)
                    frontier.append(name)
        return [name for name in self._positions if name in reached and name != sender]

    def _in_range(self, a: Position, b: Position) -> bool:
        return self._radio_range_m is None or metres_between(a, b) <= self._radio_range_m


class InMemoryMesh:
    def __init__(self, identity: str, network: InMemoryNetwork, hub_identity: str = "") -> None:
        self.identity = identity
        self._hub_identity = hub_identity
        self._network = network
        self._listeners_lock = threading.Lock()
        self._listeners: list[MessageListener] = []

    def publish(self, message: Message) -> None:
        # A Node that has left is off the air: a half-stopped one must not reach the others.
        if self._network.has_joined(self):
            self._network.deliver(self.identity, message)

    def subscribe(self, listener: MessageListener) -> None:
        with self._listeners_lock:
            self._listeners.append(listener)

    def receive(self, sender: str, message: Message) -> None:
        # Same rule as the radio: readings and Sign-ups may come from any Node, and only as
        # themselves; the rest count only from the Hub this Node was told about.
        if isinstance(message, CommunityReading | SignUp):
            if message.node != sender:
                return
        elif sender != self._hub_identity:
            return
        with self._listeners_lock:
            listeners = list(self._listeners)
        deliver_to_listeners(listeners, sender, message)
