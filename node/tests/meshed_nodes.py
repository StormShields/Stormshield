from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi.testclient import TestClient

from storm_shield.cache_pack import CachePack
from storm_shield.community_reading import CommunityReading, Measurement, Position, Reading
from storm_shield.community_warning import CommunityWarning
from storm_shield.mesh import InMemoryMesh, Message
from storm_shield.node_registry import NodeRegistryMessage, RegisteredNode, SignUp
from storm_shield.official_alert import OfficialAlert
from storm_shield.official_gauge import OfficialGaugeLevel
from storm_shield.region import Region
from storm_shield.replay import ReplayClockMessage
from storm_shield.sandbox import HUB, SimulatedNodes
from storm_shield.shelter_status import ShelterStatus


def _no_internet(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("tests never reach Open-Meteo", request=request)


def _internet_is_up(request: httpx.Request) -> httpx.Response:
    return httpx.Response(204)


def a_calm_day() -> list[Reading]:
    """One reading of each kind the rules read, made up: no storm, a metre of water."""
    now = datetime.now(UTC)
    return [
        Reading(kind=kind, value=value, unit=unit, timestamp=now)
        for kind, value, unit in [
            ("air_pressure", 1015, "hPa"),
            ("rain_rate", 0, "mm/h"),
            ("water_level", 1.0, "m"),
            ("soil_moisture", 30, "%"),
        ]
    ]


class MeshedNodes:
    """Several Nodes in one process, joined by the in-memory Mesh and driven through their APIs."""

    def __init__(self, directory: Path) -> None:
        # Every Node's files live under here, never in the checkout: a built dashboard, a downloaded
        # Cache Pack or a Hub's saved Shelter status there would change what the tests see.
        self._now = datetime.now(UTC)
        self._directory = directory
        self._nodes = SimulatedNodes(directory, clock=lambda: self._now)
        self._network = self._nodes.network
        self._hand_fed: dict[str, tuple[InMemoryMesh, int]] = {}
        self._registry_ver = 0

    def start(
        self,
        *names: str,
        cache_pack: tuple[Path, bytes] | None = None,
        loaded_region: Region | None = None,
        **overrides: Any,
    ) -> None:
        """Start Nodes that trust `HUB`; with a (directory, zip) pair each already holds that pack."""
        for name in names:
            settings = self._nodes.settings(name, hub_identity=HUB, **overrides)
            if cache_pack:
                directory, pack = cache_pack
                settings = settings.model_copy(update={"cache_pack_dir": directory / name})
                CachePack(directory / name).install(pack)
            self._nodes.start(settings, region=loaded_region)

    def start_sensor(
        self,
        name: str,
        *,
        river_km: float | None = None,
        publish_every_seconds: float = 0.02,
        sign_up_repeat_seconds: float = 10,
        cache_pack: tuple[Path, bytes] | None = None,
        **overrides: Any,
    ) -> None:
        """Start a Sensor that trusts `HUB`, with its background loops running so it keeps publishing;
        with a (directory, zip) pair it already holds that pack."""
        settings = self._nodes.settings(
            name,
            hub_identity=HUB,
            river_km=river_km,
            publish_every_seconds=publish_every_seconds,
            sign_up_repeat_seconds=sign_up_repeat_seconds,
            **overrides,
        )
        if cache_pack:
            directory, pack = cache_pack
            settings = settings.model_copy(update={"cache_pack_dir": directory / name})
            CachePack(directory / name).install(pack)
        self._nodes.start(settings, running=True)

    def start_hub(
        self,
        cache_pack: tuple[Path, bytes] | None = None,
        *,
        shelter_repeat_seconds: float = 30,
        replay_repeat_seconds: float = 10,
        alert_check_seconds: float = 0.02,
        warning_repeat_seconds: float = 10,
        loaded_region: Region | None = None,
        gauge_source: httpx.Client | None = None,
        **overrides: Any,
    ) -> None:
        """Start the Hub, whose identity is `HUB`, with its background loops running."""
        settings = self._nodes.settings(
            HUB,
            role="hub",
            shelter_repeat_seconds=shelter_repeat_seconds,
            replay_repeat_seconds=replay_repeat_seconds,
            alert_check_seconds=alert_check_seconds,
            warning_repeat_seconds=warning_repeat_seconds,
            **overrides,
        )
        if cache_pack:
            directory, pack = cache_pack
            settings = settings.model_copy(
                update={"cache_pack_dir": directory / HUB, "data_dir": directory / HUB / "data"}
            )
            CachePack(directory / HUB).install(pack)
        weather_source = httpx.Client(transport=httpx.MockTransport(_no_internet))
        self._nodes.start(
            settings,
            running=True,
            weather_source=weather_source,
            region=loaded_region,
            # Online, so a Hub given a `gauge_source` polls it; nothing else here asks the internet.
            internet_source=httpx.Client(transport=httpx.MockTransport(_internet_is_up)),
            **({"gauge_source": gauge_source} if gauge_source else {}),
        )

    def data_dir(self, name: str) -> Path:
        """Where a Node keeps its saved files."""
        return self._directory / name / "data"

    def stop_hub(self) -> None:
        """Stop the Hub as a power cut would; `start_hub` with the same directory brings it back."""
        self._nodes.stop(HUB)

    def close(self) -> None:
        self._nodes.close()

    def announce_replay(
        self, state: Literal["playing", "paused", "stopped"], event_t: int, *, sender: str = HUB
    ) -> None:
        """Have a Node that is not running an app publish one Event clock message."""
        self._hand_fed_mesh(sender).publish(
            ReplayClockMessage(event="bhote-koshi-2026", state=state, event_t=event_t, rate=30)
        )

    def announce_shelters(self, ver: int, open_ids: list[str], *, sender: str = HUB) -> None:
        """Have a Node that is not running an app publish one Shelter status."""
        self._hand_fed_mesh(sender).publish(
            ShelterStatus(ver=ver, t=int(self._now.timestamp()), open=open_ids)
        )

    def announce_registry(
        self, ver: int, names: list[str], *, sender: str = HUB, of: int = 1
    ) -> None:
        """Have a Node that is not running an app publish one Node registry; a name is its own id."""
        self._hand_fed_mesh(sender).publish(
            NodeRegistryMessage(
                ver=ver,
                of=of,
                t=int(self._now.timestamp()),
                nodes=[RegisteredNode(id=name, name=name) for name in names],
            )
        )

    def announce_sign_up(self, node: str, name: str) -> None:
        """Have a Node that is not running an app publish its Sign-up."""
        self._hand_fed_mesh(node).publish(SignUp(node=node, name=name))

    def register(self, *names: str) -> None:
        """Have the Hub's registry list these Nodes (and the Hub), so their readings count."""
        self._registry_ver += 1
        self.announce_registry(self._registry_ver, [HUB, *names])

    def announce_official_alert(self, alert: OfficialAlert, *, sender: str = HUB) -> None:
        """Have a Node that is not running an app publish one Official Alert."""
        self._hand_fed_mesh(sender).publish(alert)

    def announce_official_gauge(self, level: OfficialGaugeLevel, *, sender: str = HUB) -> None:
        """Have a Node that is not running an app publish one Official Gauge level."""
        self._hand_fed_mesh(sender).publish(level)

    def announce_community_warning(self, warning: CommunityWarning, *, sender: str = HUB) -> None:
        """Have a Node that is not running an app publish one Community Warning."""
        self._hand_fed_mesh(sender).publish(warning)

    def send_bytes(self, body: bytes, *, sender: str = HUB) -> None:
        """Put exactly these bytes on the Mesh, as a Node running other software could."""
        # Joining first means the sender is not among the receivers, as when it publishes.
        self._hand_fed_mesh(sender)
        self._network.deliver_bytes(sender, body)

    def join_with_failing_listener(self, name: str) -> None:
        """Join a Node whose listener raises on every message."""

        def fail(_sender: str, _message: Message) -> None:
            raise RuntimeError("bug in one listener")

        self._network.join(name, HUB).subscribe(fail)

    def _hand_fed_mesh(self, sender: str) -> InMemoryMesh:
        """The Mesh of a Node that is not running an app, joined on first use."""
        mesh = self._hand_fed.get(sender) or (self._network.join(sender), 0)
        self._hand_fed[sender] = mesh
        return mesh[0]

    def record_shelter_status(self) -> list[ShelterStatus]:
        """Join a Node that only listens; every Shelter status it hears is appended to the list."""
        heard: list[ShelterStatus] = []
        mesh = self._network.join("recorder", HUB)
        mesh.subscribe(
            lambda _, message: heard.append(message) if isinstance(message, ShelterStatus) else None
        )
        return heard

    def advance(self, seconds: float) -> None:
        """Move every Node's clock forward without waiting."""
        self._now += timedelta(seconds=seconds)

    def hear_from(
        self,
        sender: str,
        *,
        pressure_hpa: float = 1015,
        rain_mmh: float = 0,
        water_cm: float = 20,
        soil_pct: float = 30,
        river_km: float | None = None,
        leaving_out: Collection[str] = (),
        also: Collection[Measurement] = (),
        simulated: bool = True,
    ) -> None:
        """Have a Node that is not running an app publish one reading with exactly these values.

        `simulated=False` stands in for a Sensor with real hardware, which nothing produces yet.

        The Event's surface cannot make soil moisture rise while the water stays low, so this
        reaches the rules it cannot. `leaving_out` drops kinds the Node does not measure; `also` adds
        Measurements, such as a kind the rules do not know or a known kind in another unit.
        """
        mesh, seq = self._hand_fed.get(sender) or (self._network.join(sender), 0)
        self._hand_fed[sender] = (mesh, seq + 1)
        mesh.publish(
            CommunityReading(
                node=sender,
                seq=seq + 1,
                t=int(self._now.timestamp()),
                sim=simulated,
                pos=Position(29.652, -82.324),
                river_km=river_km,
                m=[
                    measurement
                    for measurement in [
                        Measurement("air_pressure", pressure_hpa, "hPa"),
                        Measurement("water_level", water_cm / 100, "m"),
                        Measurement("rain_rate", rain_mmh, "mm/h"),
                        Measurement("soil_moisture", soil_pct, "%"),
                    ]
                    if measurement.kind not in leaving_out
                ]
                + list(also),
            )
        )

    def remove(self, name: str) -> None:
        self._nodes.stop(name)

    def __getitem__(self, name: str) -> TestClient:
        return self._nodes[name]
