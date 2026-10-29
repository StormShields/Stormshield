import argparse
import itertools
import json
import logging
import subprocess
import threading
import time
import webbrowser
from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Any, NamedTuple, Self, cast

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from storm_shield.cache_pack import CachePack, InvalidCachePack, download_source
from storm_shield.community_reading import Position
from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.region import Region, load_region, region_names, region_path
from storm_shield.river_line import river_km_at
from storm_shield.sandbox_api import (
    SandboxControls,
    SandboxNode,
    SandboxNodes,
    SandboxRefused,
    SandboxRegion,
    SandboxRegions,
    Spot,
    UnknownSensor,
)
from storm_shield.settings import Settings

logger = logging.getLogger(__name__)

HUB = "hub"
# Wide enough for the Region's sensor sites, whose longest gap is about 33 km. When the Sandbox
# places its Sensors on a Region's sites (#46) this becomes the 1 km the spec asks for.
SANDBOX_RADIO_RANGE_M = 40_000.0
DOWNLOAD_TIMEOUT_SECONDS = 120
REPO = Path(__file__).resolve().parents[3]
BUILT_DASHBOARD = REPO / "dashboard" / "dist" / "index.html"


class NodeSite(NamedTuple):
    name: str
    latitude: float
    longitude: float
    river_km: float | None


def sites_of(region: Region) -> tuple[NodeSite, list[NodeSite]]:
    """Where the Region's Hub runs, and its suggested sensor sites in the file's order: nearest the
    Hub first, because a Node's first reading goes out as it joins and only reaches the Hub if the
    Nodes between are already there. Sensors are named s0, s1, ...: the Region's site ids are long,
    and nine of them would not fit the one signed packet a registry travels in."""
    hub = NodeSite(HUB, region.hub_site.pos[0], region.hub_site.pos[1], region.hub_site.river_km)
    sensors = [
        NodeSite(f"s{number}", site.pos[0], site.pos[1], site.river_km)
        for number, site in enumerate(region.sensor_sites)
    ]
    return hub, sensors


HUB_SITE, SENSOR_SITES = sites_of(load_region(region_path(Settings().region)))


class SandboxError(Exception):
    """The Sandbox cannot start; the message says what to do about it."""


class SimulatedNodes:
    """Nodes in this process on one in-memory Mesh: the harness under the Sandbox and the tests.

    Each Node keeps its files in its own folder under `directory`, and all of them read `clock`.
    The radio range is unlimited unless the caller sets one.
    """

    def __init__(
        self,
        directory: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        radio_range_m: float | None = None,
    ) -> None:
        self.network = InMemoryNetwork(radio_range_m=radio_range_m)
        self._directory = directory
        self._clock = clock
        self._clients: dict[str, TestClient] = {}
        self._settings: dict[str, Settings] = {}
        self._running: set[str] = set()

    def settings(self, name: str, **overrides: Any) -> Settings:
        """A Node's settings: its own folders, and no dashboard."""
        own = self._directory / name
        return Settings(
            **{
                "name": name,
                "dashboard_dir": own / "no-dashboard",
                "cache_pack_dir": own / "cache-pack",
                "data_dir": own / "data",
                **overrides,
            }
        )

    def start(self, settings: Settings, *, running: bool = False, **app_options: Any) -> TestClient:
        """Join the Mesh and build the Node, which trusts `HUB`.

        With `running` the Node's background loops start, so it keeps publishing until `stop` or
        `close`; otherwise it only answers requests.
        """
        mesh = self.network.join(
            settings.name, HUB, Position(settings.latitude, settings.longitude)
        )
        app = create_app(settings, mesh, clock=self._clock, **app_options)
        client = TestClient(app)
        if running:
            client.__enter__()
            self._running.add(settings.name)
        self._clients[settings.name] = client
        self._settings[settings.name] = settings
        return client

    def move(self, name: str, spot: Spot, river_km: float | None) -> None:
        """Put a Node at `spot` on the Mesh and have it read, and share a reading, from there."""
        settings = self._settings[name]
        # The Node reads its spot from its settings each time it shares.
        settings.latitude, settings.longitude, settings.river_km = (
            spot.latitude,
            spot.longitude,
            river_km,
        )
        self.network.move(name, Position(spot.latitude, spot.longitude))
        cast(FastAPI, self._clients[name].app).state.share_reading()

    def stop(self, name: str) -> None:
        """Take a Node off the Mesh as a power cut would; starting it again keeps its folder."""
        client = self._clients.pop(name)
        del self._settings[name]
        if name in self._running:
            self._running.remove(name)
            client.__exit__(None, None, None)
        self.network.leave(name)

    def close(self) -> None:
        for name in list(self._running):
            self._clients[name].__exit__(None, None, None)
        self._running.clear()

    def __getitem__(self, name: str) -> TestClient:
        return self._clients[name]


class _Switchboard:
    """The app the Sandbox serves: whichever Hub is current, so a Region switch swaps the Hub
    without restarting the server. The Hub's own loops run in its test client, so this answers the
    server's lifespan itself."""

    def __init__(self) -> None:
        self.app: FastAPI

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "lifespan":
            await self.app(scope, receive, send)
            return
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


class Sandbox:
    """A Hub and simulated Sensors in this process on one in-memory Mesh, already registered.

    Everything the Nodes write lives in a temporary folder that is removed on exit. The Sensors
    run their loops here; the caller serves `hub` (or drives it with a TestClient). `network` is the
    Mesh they share, for a caller that needs to put a message on it.

    Switching Region starts a whole new Mesh from that Region's pack, found by `find_pack`, and
    swaps it in under `hub`; the old one is closed once the new one is up.
    """

    def __init__(
        self,
        pack: Path,
        region: str | None = None,
        *,
        find_pack: Callable[[str], Path] | None = None,
    ) -> None:
        _require_pack(pack)
        self._first = (region or Settings().region, pack)
        self._find_pack = find_pack
        # Shared with the Hub's controls, so a Sensor is never edited on a Mesh that is being replaced.
        self._lock = threading.RLock()
        self._stack = ExitStack()
        self.hub = _Switchboard()
        self.network: InMemoryNetwork

    def __enter__(self) -> Self:
        self._stack, self.hub.app, self.network = self._start(*self._first)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stack.close()

    def _start(self, region: str, pack: Path) -> tuple[ExitStack, FastAPI, InMemoryNetwork]:
        _require_pack(pack)
        pack_bytes = pack.read_bytes()
        hub_site, sensor_sites = sites_of(load_region(region_path(region)))
        with ExitStack() as setup:
            directory = Path(
                setup.enter_context(TemporaryDirectory(prefix="storm-shield-sandbox-"))
            )
            nodes = SimulatedNodes(directory, radio_range_m=SANDBOX_RADIO_RANGE_M)
            setup.callback(nodes.close)
            hub_client = self._start_hub(
                nodes, hub_site, region, pack, pack_bytes, len(sensor_sites)
            )
            # Running starts a Sensor's loops, so it keeps publishing. All of them join before any
            # signs up: a Sensor out of the Hub's own range needs its neighbours to relay.
            sensors = {site.name: _start_sensor(nodes, site, pack_bytes) for site in sensor_sites}
            for name, sensor in sensors.items():
                # An in-memory Node's id is its name.
                _register(sensor, hub_client, name)
            return setup.pop_all(), cast(FastAPI, hub_client.app), nodes.network

    def _start_hub(
        self,
        nodes: SimulatedNodes,
        site: NodeSite,
        region: str,
        pack: Path,
        pack_bytes: bytes,
        sensors_placed: int,
    ) -> TestClient:
        settings = _settings(
            nodes, site, role="hub", region=region, dashboard_dir=BUILT_DASHBOARD.parent
        )
        try:
            CachePack(settings.cache_pack_dir).install(pack_bytes)
        except InvalidCachePack as error:
            raise SandboxError(f"{pack} is not a usable Cache Pack: {error}") from error
        river = CachePack(settings.cache_pack_dir).file("river.geojson")
        return nodes.start(
            settings,
            running=True,
            sandbox=_Controls(
                nodes,
                pack_bytes,
                json.loads(river.read_text()) if river else None,
                region,
                sensors_placed,
                self._switch_region,
                self._lock,
            ),
        )

    def _switch_region(self, region: str) -> None:
        with self._lock:
            if self._find_pack is None:
                raise SandboxRefused("this Sandbox has no way to find another Region's Cache Pack")
            try:
                stack, hub, network = self._start(region, self._find_pack(region))
            except SandboxError as error:
                raise SandboxRefused(str(error)) from None
            old = self._stack
            self._stack, self.hub.app, self.network = stack, hub, network
            old.close()


def _require_pack(pack: Path) -> None:
    if not pack.is_file():
        raise SandboxError(
            f"no Cache Pack at {pack}; build one with scripts/build-cache-pack.sh or drop --pack"
        )


class _Controls(SandboxControls):
    """What the Hub's Sandbox API shows and changes: the Sensors, the radio range, who hears whom.

    `pack` is what each Sensor holds, as if it had downloaded it from the Hub; `river` is its river
    line, which tells a Sensor placed on the map its River km.
    """

    def __init__(
        self,
        nodes: SimulatedNodes,
        pack: bytes,
        river: dict[str, Any] | None,
        region: str,
        sensors_placed: int,
        switch_region: Callable[[str], None],
        lock: threading.RLock,
    ) -> None:
        self._nodes = nodes
        self._pack = pack
        self._river = river
        self._region = region
        self._switch_region = switch_region
        # The API runs on a threadpool: a Sensor being added is half on the Mesh until it is done.
        self._lock = lock
        # Sensors are numbered on from the Sandbox's own and never reused: a Sensor that came
        # back under an old id would restart its readings at seq 0, and the Hub would hide them.
        self._numbers = itertools.count(sensors_placed)
        # Sensors with no path to the Hub when they were placed: it cannot hear them sign up.
        self._unregistered: set[str] = set()

    def nodes(self) -> SandboxNodes:
        with self._lock:
            radio_range_m = self._nodes.network.radio_range_m
            if radio_range_m is None:
                raise RuntimeError("the Sandbox always runs with a radio range")
            links = self._nodes.network.links(HUB)
            states = {name: self._nodes[name].get("/api/state").json() for name in links}
            newest_warning = max((w["id"] for w in states[HUB]["community_warnings"]), default=None)
            return SandboxNodes(
                radio_range_m=radio_range_m,
                nodes=[
                    SandboxNode(
                        id=name,
                        name=states[name]["name"],
                        role=states[name]["role"],
                        position=reach.position,
                        links=reach.in_range,
                        hops=reach.hops_from_hub,
                        heard_warning=newest_warning is not None
                        and newest_warning in {w["id"] for w in states[name]["community_warnings"]},
                    )
                    for name, reach in links.items()
                ],
            )

    def set_radio_range(self, radio_range_m: float) -> SandboxNodes:
        with self._lock:
            self._nodes.network.set_radio_range(radio_range_m)
            self._register_those_in_reach()
            return self.nodes()

    def add_sensor(self, spot: Spot) -> SandboxNodes:
        with self._lock:
            name = f"s{next(self._numbers)}"
            site = NodeSite(name, spot.latitude, spot.longitude, self._river_km(spot))
            _start_sensor(self._nodes, site, self._pack)
            self._unregistered.add(name)
            try:
                self._register_those_in_reach()
            except SandboxRefused:
                # A Sensor the Hub will not take would sit there never counting.
                self._nodes.stop(name)
                self._unregistered.discard(name)
                raise
            return self.nodes()

    def move_sensor(self, sensor_id: str, spot: Spot) -> SandboxNodes:
        with self._lock:
            self._require_sensor(sensor_id)
            self._nodes.move(sensor_id, spot, self._river_km(spot))
            self._register_those_in_reach()
            return self.nodes()

    def remove_sensor(self, sensor_id: str) -> SandboxNodes:
        with self._lock:
            self._require_sensor(sensor_id)
            self._nodes.stop(sensor_id)
            self._unregistered.discard(sensor_id)
            return self.nodes()

    def regions(self) -> SandboxRegions:
        return SandboxRegions(
            current=self._region,
            regions=[
                SandboxRegion(name=name, label=load_region(region_path(name)).label)
                for name in region_names()
            ],
        )

    def switch_region(self, region: str) -> SandboxRegions:
        if region not in region_names():
            raise SandboxRefused(f"there is no Region {region!r}")
        # The Hub this runs on is closed by the switch, so the answer comes from the new one.
        self._switch_region(region)
        return SandboxRegions(current=region, regions=self.regions().regions)

    def _require_sensor(self, sensor_id: str) -> None:
        if sensor_id == HUB or sensor_id not in self._nodes.network.links(HUB):
            raise UnknownSensor(sensor_id)

    def _river_km(self, spot: Spot) -> float | None:
        return (
            river_km_at(self._river, Position(spot.latitude, spot.longitude))
            if self._river
            else None
        )

    def _register_those_in_reach(self) -> None:
        """Sign up and accept each unregistered Sensor the Hub can now hear."""
        hops = {name: reach.hops_from_hub for name, reach in self._nodes.network.links(HUB).items()}
        for name in sorted(self._unregistered):
            if hops.get(name) is None:
                continue
            try:
                _register(self._nodes[name], self._nodes[HUB], name)
            except httpx.HTTPStatusError as error:
                raise SandboxRefused(
                    f"the Hub would not register {name}: {error.response.json()['detail']}"
                ) from None
            self._unregistered.discard(name)


def _settings(nodes: SimulatedNodes, site: NodeSite, **overrides: Any) -> Settings:
    return nodes.settings(
        site.name,
        latitude=site.latitude,
        longitude=site.longitude,
        river_km=site.river_km,
        hub_identity=HUB,
        **overrides,
    )


def _start_sensor(nodes: SimulatedNodes, site: NodeSite, pack: bytes) -> TestClient:
    """A running Sensor that already holds the Cache Pack: a coast Sensor reads its ground height
    from the pack's terrain, and would stay dry until it had downloaded one."""
    settings = _settings(nodes, site)
    CachePack(settings.cache_pack_dir).install(pack)
    return nodes.start(settings, running=True)


def _register(sensor: TestClient, hub: TestClient, sensor_id: str) -> None:
    """Sign the Sensor up and accept it, so its readings count at once."""
    sensor.post("/api/registry/signup").raise_for_status()
    hub.post("/api/registry/accept", json={"id": sensor_id}).raise_for_status()


def _open_browser_when_up(server: uvicorn.Server, url: str) -> None:
    while not server.started:
        time.sleep(0.1)
    webbrowser.open(url)


def pack_for(region: str, client: httpx.Client, override: str = "") -> Path:
    """The Region's Cache Pack: the one its build command wrote, else the one fetched from its
    Release on an earlier run, else the Release itself. Says which command to run when none is
    there."""
    built = REPO / "node" / "build" / region / "cache-pack.zip"
    if built.is_file():
        return built
    downloaded = REPO / ".demo" / "pack" / region / "cache-pack.zip"
    if downloaded.is_file():
        return downloaded
    build_command = f"scripts/build-cache-pack.sh {region}"
    url = download_source(override, region)
    if not url:
        raise SandboxError(
            f"no Cache Pack for the {region} Region on disk or published as a Release; "
            f"build one with `{build_command}`"
        )
    logger.info("downloading the %s Cache Pack to %s (once)", region, downloaded)
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        # The error text carries the URL; the type is enough to tell offline from refused.
        raise SandboxError(
            f"could not download the {region} Cache Pack ({type(error).__name__}); connect to the"
            f" internet once, build one with `{build_command}`, or pass --pack"
        ) from None
    downloaded.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the final name, so an interrupted download is not mistaken for the pack.
    partial = downloaded.with_name(downloaded.name + ".part")
    partial.write_bytes(response.content)
    partial.rename(downloaded)
    return downloaded


def build_dashboard_if_missing() -> None:
    """Build the dashboard the Hub serves, the first time only."""
    if BUILT_DASHBOARD.is_file():
        return
    logger.info("building the dashboard (once)")
    dashboard = REPO / "dashboard"
    try:
        for command in (["pnpm", "install", "--frozen-lockfile"], ["pnpm", "build"]):
            subprocess.run(command, cwd=dashboard, check=True, capture_output=True)
    except FileNotFoundError:
        raise SandboxError("pnpm is not installed, and the dashboard needs building once") from None
    except subprocess.CalledProcessError as error:
        raise SandboxError(
            f"`{' '.join(error.cmd)}` failed in dashboard/:\n{error.stderr.decode()[-2000:]}"
        ) from None


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx logs request URLs at INFO, and the Release download's URL is signed.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        prog="storm-shield-sandbox",
        description="Start a Hub and simulated Sensors in one process and open the dashboard.",
    )
    parser.add_argument("--port", type=int, default=8000, help="where the dashboard is served")
    parser.add_argument(
        "--region",
        choices=region_names(),
        default=Settings().region,
        help="the Region to start on (the dashboard can switch)",
    )
    parser.add_argument(
        "--pack",
        type=Path,
        help="a Cache Pack zip to use instead of the Region's built or published one",
    )
    arguments = parser.parse_args()
    try:
        with httpx.Client(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
            cache_pack_url = Settings().cache_pack_url

            def find_pack(region: str) -> Path:
                return pack_for(region, client, cache_pack_url)

            pack = arguments.pack or find_pack(arguments.region)
            build_dashboard_if_missing()
            with Sandbox(pack, arguments.region, find_pack=find_pack) as sandbox:
                server = uvicorn.Server(uvicorn.Config(sandbox.hub, port=arguments.port))
                url = f"http://localhost:{arguments.port}"
                logger.info("Sandbox dashboard: %s (everything in it is SIMULATED)", url)
                threading.Thread(
                    target=_open_browser_when_up, args=(server, url), daemon=True
                ).start()
                server.run()
    except SandboxError as error:
        raise SystemExit(f"storm-shield-sandbox: {error}") from None
