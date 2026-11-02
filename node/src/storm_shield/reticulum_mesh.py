import logging
import os
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import RNS

from storm_shield.community_reading import CommunityReading
from storm_shield.mesh import (
    Message,
    MessageListener,
    decode_message,
    deliver_to_listeners,
    refuse_over_one_packet,
)
from storm_shield.node_registry import SignUp
from storm_shield.settings import Settings

APP_NAME = "storm_shield"
ANNOUNCE_EVERY_SECONDS = 10
NODE_ID_LENGTH = 12
SIGNATURE_LENGTH = 64

# Slot n listens on LOOPBACK_BASE_PORT + n and dials every lower slot of its group, so each pair of
# Nodes in a group shares exactly one connection. A hub-and-spoke layout does not work: Reticulum
# does not pass one client's broadcast on to another client.
LOOPBACK_BASE_PORT = 4250

logger = logging.getLogger(__name__)


def node_id(identity: Any) -> str:
    return str(identity.hexhash[:NODE_ID_LENGTH])


def reticulum_config(settings: Settings) -> str:
    return f"""[reticulum]
  enable_transport = False
  share_instance = No

[logging]
  loglevel = 2

[interfaces]
{_interface_config(settings)}
"""


_WIFI_DISCOVERY = "  [[Wi-Fi]]\n    type = AutoInterface\n    enabled = yes"


def _interface_config(settings: Settings) -> str:
    blocks = [_primary_interface(settings)]
    if settings.also_wifi_discovery and settings.mesh_interface != "auto":
        blocks.append(_WIFI_DISCOVERY)
    if settings.also_tcp_listen and settings.mesh_interface != "tcp":
        blocks.append(_tcp_listen("0.0.0.0", settings.tcp_port, name="Clients"))
    return "\n".join(blocks)


def _tcp_listen(listen_ip: str, listen_port: int, name: str = "Listen") -> str:
    return (
        f"  [[{name}]]\n    type = TCPServerInterface\n    enabled = yes\n"
        f"    listen_ip = {listen_ip}\n    listen_port = {listen_port}"
    )


def _primary_interface(settings: Settings) -> str:
    if settings.mesh_interface == "auto":
        return _WIFI_DISCOVERY
    if settings.mesh_interface == "tcp":
        listen_ip, listen_port = "0.0.0.0", settings.tcp_port
        dials = [_peer_address(entry, settings.tcp_port) for entry in _entries(settings.tcp_peers)]
    else:
        if not 0 <= settings.loopback_first_slot <= settings.loopback_slot:
            raise ValueError(
                f"NODE_LOOPBACK_FIRST_SLOT {settings.loopback_first_slot} must be between 0 and "
                f"NODE_LOOPBACK_SLOT {settings.loopback_slot}"
            )
        listen_ip, listen_port = "127.0.0.1", LOOPBACK_BASE_PORT + settings.loopback_slot
        dials = [
            ("127.0.0.1", LOOPBACK_BASE_PORT + slot)
            for slot in range(settings.loopback_first_slot, settings.loopback_slot)
        ]
    dial_peers = [
        f"  [[Peer {number}]]\n    type = TCPClientInterface\n    enabled = yes\n"
        f"    target_host = {host}\n    target_port = {port}"
        for number, (host, port) in enumerate(dials)
    ]
    return "\n".join([_tcp_listen(listen_ip, listen_port), *dial_peers])


def _entries(peers: str) -> list[str]:
    return [entry.strip() for entry in peers.split(",") if entry.strip()]


def _peer_address(entry: str, default_port: int) -> tuple[str, int]:
    host, _, port = entry.partition(":")
    if port and not port.isdigit():
        raise ValueError(f"NODE_TCP_PEERS entry {entry!r} must be host or host:port")
    return (host, int(port) if port else default_port)


def sign(identity: Any, message: Message) -> bytes:
    """Signature then JSON: Reticulum does not say who sent a data packet, so the Node does."""
    body = message.model_dump_json().encode()
    return bytes(identity.sign(body)) + body


def verify(
    data: bytes, known_nodes: Mapping[str, Any], hub_identity: str = ""
) -> tuple[str, Message] | None:
    """The verified sender and message, or None if it is unknown, forged or not from who may send it.

    A reading or a Sign-up names its Node. Every other kind names nobody, so it must verify
    against the Hub key.
    """
    if len(data) <= SIGNATURE_LENGTH:
        return None
    signature, body = data[:SIGNATURE_LENGTH], data[SIGNATURE_LENGTH:]
    message = decode_message(body)
    if message is None:
        return None
    sender_id = message.node if isinstance(message, CommunityReading | SignUp) else hub_identity
    sender = known_nodes.get(sender_id)
    # Nothing to log for an unknown sender: until its announce arrives that is the normal case.
    if sender is None:
        return None
    if not sender.validate(signature, body):
        logger.warning(
            "dropped a %s whose signature does not match Node %s", message.kind, sender_id
        )
        return None
    return sender_id, message


class ReticulumMesh:
    """Mesh messages as signed, unencrypted broadcast packets; Nodes learn each other from announces."""

    def __init__(self, settings: Settings) -> None:
        config_dir = settings.data_dir / "reticulum"
        config_dir.mkdir(parents=True, exist_ok=True)
        # Rewritten on every start so the settings, not a stale file, decide the interface.
        (config_dir / "config").write_text(reticulum_config(settings))
        RNS.Reticulum(configdir=str(config_dir), loglevel=RNS.LOG_WARNING)

        self._key = load_or_create_identity(settings.data_dir / "identity")
        self.identity = node_id(self._key)
        self._hub_identity = settings.hub_identity
        self._known_nodes: dict[str, Any] = {}
        self._listeners: list[MessageListener] = []
        self._send_failing = False

        self._announce_destination = RNS.Destination(
            self._key, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, "node"
        )
        RNS.Transport.register_announce_handler(_NodeAnnounces(self._known_nodes))

        readings_in = RNS.Destination(
            None, RNS.Destination.IN, RNS.Destination.PLAIN, APP_NAME, "readings"
        )
        readings_in.set_packet_callback(self._on_packet)
        self._readings_out = RNS.Destination(
            None, RNS.Destination.OUT, RNS.Destination.PLAIN, APP_NAME, "readings"
        )

        threading.Thread(target=self._announce_forever, daemon=True).start()

    def publish(self, message: Message) -> None:
        packet = sign(self._key, message)
        refuse_over_one_packet(len(packet))
        sent = bool(RNS.Packet(self._readings_out, packet).send())
        # Log only when sending starts or stops failing: a Node with no peers
        # fails on every publish, and a warning each time buries the real logs.
        if not sent and not self._send_failing:
            logger.warning(
                "Reticulum cannot send this Node's %s (no peers or interfaces?)", message.kind
            )
        elif sent and self._send_failing:
            logger.info("Reticulum is sending this Node's messages again")
        self._send_failing = not sent

    def subscribe(self, listener: MessageListener) -> None:
        self._listeners.append(listener)

    def _on_packet(self, data: bytes, _packet: Any) -> None:
        verified = verify(data, self._known_nodes, self._hub_identity)
        if verified is None:
            return
        sender, message = verified
        deliver_to_listeners(self._listeners, sender, message)

    def _announce_forever(self) -> None:
        while True:
            try:
                self._announce_destination.announce()
            except Exception:
                # One failed announce must not make this Node undiscoverable for good.
                logger.exception("could not announce this Node")
            time.sleep(ANNOUNCE_EVERY_SECONDS)


class _NodeAnnounces:
    aspect_filter = f"{APP_NAME}.node"

    def __init__(self, known_nodes: dict[str, Any]) -> None:
        self._known_nodes = known_nodes

    def received_announce(
        self,
        destination_hash: bytes,
        announced_identity: Any,
        app_data: bytes | None,
        announce_packet_hash: bytes | None = None,
    ) -> None:
        self._known_nodes[node_id(announced_identity)] = announced_identity


def load_or_create_identity(path: Path) -> Any:
    """This Node's identity. The file holds its private key, so only its owner may read it."""
    if path.exists():
        key = RNS.Identity.from_file(str(path))
        if key is None:
            raise ValueError(
                f"{path} is not a Reticulum identity (a write cut short?). Delete it to give this "
                "Node a new id; if it is the Hub, every Node then needs the new HUB_IDENTITY"
            )
        # Identity files written before this check are readable by everyone on the machine.
        path.chmod(0o600)
        return key
    key = RNS.Identity()
    # Not Identity.to_file: it leaves the key readable by everyone and only logs a failed write.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
        file.write(key.get_private_key())
    return key
