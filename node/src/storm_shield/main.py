import asyncio
import logging
import struct
import threading
import zlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from storm_shield.cache_pack import (
    DOWNLOAD_TIMEOUT_SECONDS,
    RETRY_EVERY_SECONDS,
    CachePack,
    download_source,
)
from storm_shield.community_reading import CommunityReading, Position, Reading, fuzz_position
from storm_shield.community_warning import CommunityWarning, HeardCommunityWarnings, HubWarnings
from storm_shield.flood_email import FloodEmail
from storm_shield.flood_risk import FloodRisk, flood_risk, warning_triggers
from storm_shield.internet_connection import (
    CONNECTIVITY_TIMEOUT_SECONDS,
    InternetConnection,
    Status,
)
from storm_shield.mesh import InMemoryNetwork, Mesh, Message
from storm_shield.node_registry import (
    NODE_NAME_MAX_LENGTH,
    HeardRegistry,
    HubRegistry,
    NodeRegistryMessage,
    NoWaitingSignUp,
    RegisteredNode,
    RegistrationState,
    RegistryFull,
    RegistrySummary,
    SignUp,
)
from storm_shield.official_alert import HeardOfficialAlerts, OfficialAlert
from storm_shield.official_gauge import (
    NOAA_TIMEOUT_SECONDS,
    HeardOfficialGauges,
    OfficialGaugeLevel,
    read_noaa_level,
)
from storm_shield.reading_publisher import ReadingPublisher
from storm_shield.reading_store import NodeSnapshot, ReadingStore
from storm_shield.region import (
    Coast,
    Hazard,
    OfficialGauge,
    Region,
    RegionSummary,
    load_region,
    region_path,
)
from storm_shield.replay import Event, EventClock, ReplayClockMessage, SensorSpot, load_events
from storm_shield.reticulum_mesh import ReticulumMesh
from storm_shield.sandbox_api import (
    RadioRange,
    SandboxControls,
    SandboxNodes,
    SandboxRefused,
    Spot,
    UnknownSensor,
)
from storm_shield.settings import Role, Settings
from storm_shield.shelter_status import (
    HeardShelterStatus,
    ShelterRegistry,
    ShelterStatus,
    UnknownShelter,
)
from storm_shield.terrain import elevation_at
from storm_shield.timing import REPLAY_PUBLISH_EVERY_SECONDS
from storm_shield.weather_forecast import FORECAST_TIMEOUT_SECONDS, WeatherForecast

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
CARTO_TILE_URL = "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png"
TILE_TIMEOUT_SECONDS = 10

logger = logging.getLogger(__name__)


class NodeEntry(NodeSnapshot):
    """A Node's latest readings plus whether it counts; `name` is its registry name."""

    registered: bool
    name: str | None


class SandboxState(BaseModel):
    """Present in `/api/state` only in the Sandbox, where nothing is a real reading."""

    label: Literal["SIMULATED"] = "SIMULATED"


class OfficialGaugeState(BaseModel):
    """An Official Gauge of the Region with the newest level this Node has heard; None before any."""

    agency: str
    station: str
    label: str
    pos: tuple[float, float]
    level_m: float | None
    observed: int | None


class NodeState(BaseModel):
    id: str
    name: str
    role: Role
    status: Status
    registration: RegistrationState
    sandbox: SandboxState | None
    region: RegionSummary
    hazard: Hazard
    live: bool
    flood_risk: FloodRisk
    nodes: list[NodeEntry]
    official_alerts: list[OfficialAlert]
    community_warnings: list[CommunityWarning]
    official_gauges: list[OfficialGaugeState]


class OpenShelters(BaseModel):
    open: list[str]


class WarningLog(BaseModel):
    warnings: list[CommunityWarning]


class RegistryAccept(BaseModel):
    id: str


class ShelterChange(BaseModel):
    id: str
    open: bool


class ReplayJump(BaseModel):
    phase: str
    # Absent: the Event on the Event clock. A stopped clock names none, so the picker sends it.
    event: str | None = None


class ReplayRate(BaseModel):
    # Slower than x5 stretches S0's 3.5 m rise past the 60 s Surge window, so no warning would fire.
    rate: Literal[5, 10, 30]


class ReplayPhase(BaseModel):
    id: str
    label: str
    event_t: int


class ReplayStart(BaseModel):
    # Absent: replay the Event the Event clock names (the first Event on a Node never started).
    event: str | None = None


class ReplayEventSummary(BaseModel):
    id: str
    label: str


class ReplayEvents(BaseModel):
    events: list[ReplayEventSummary]


class ReplayPhases(BaseModel):
    phases: list[ReplayPhase]
    internet_cue_event_t: int


class CachePackStatus(BaseModel):
    available: bool
    manifest: dict[str, Any] | None


def _region_of(settings: Settings, cache_pack: CachePack) -> Region:
    """A Sensor Node's Region is the one in the pack it holds, from the Hub; a Hub's is its own."""
    in_pack = cache_pack.file("region.json")
    if settings.role == "sensor" and in_pack is not None:
        return load_region(in_pack)
    return load_region(region_path(settings.region))


def _gauge_state(gauge: OfficialGauge, level: OfficialGaugeLevel | None) -> OfficialGaugeState:
    return OfficialGaugeState(
        agency=gauge.agency,
        station=gauge.station,
        label=gauge.label,
        pos=gauge.pos,
        level_m=level.level_m if level else None,
        observed=level.observed if level else None,
    )


def create_app(
    settings: Settings,
    mesh: Mesh,
    pack_source: httpx.Client | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    tile_source: httpx.Client | None = None,
    internet_source: httpx.Client | None = None,
    weather_source: httpx.Client | None = None,
    gauge_source: httpx.Client | None = None,
    sandbox: SandboxControls | None = None,
    region: Region | None = None,
) -> FastAPI:
    cache_pack = CachePack(settings.cache_pack_dir)
    region = region or _region_of(settings, cache_pack)
    rules = region.rules.flood_warning
    weather_forecast = WeatherForecast(settings.data_dir, region.bbox)
    weather_source = weather_source or httpx.Client(
        timeout=FORECAST_TIMEOUT_SECONDS, follow_redirects=True
    )
    pack_source = pack_source or httpx.Client(
        timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
    )
    gauge_source = gauge_source or httpx.Client(timeout=NOAA_TIMEOUT_SECONDS)
    tile_source = tile_source or httpx.Client(timeout=TILE_TIMEOUT_SECONDS)
    internet = InternetConnection(
        internet_source or httpx.Client(timeout=CONNECTIVITY_TIMEOUT_SECONDS)
    )
    # httpx logs every request URL at INFO, and a tile URL carries the CARTO key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    store = ReadingStore(rules.water_levels.rising_window_s)
    events = load_events(region)
    first_event = next(iter(events.values()))
    event_clock = EventClock(first_event.id)

    def clocked_event() -> Event:
        """The Event the Event clock names; the first one while it names none this Node holds."""
        return events.get(event_clock.current(clock()).event, first_event)

    measured_kinds = {kind.strip() for kind in settings.measures.split(",") if kind.strip()}
    # Read once per spot and pack, not at every share; a new pack or a Sandbox move reads again.
    ground_heights: dict[Position, float | None] = {}
    ground_heights_pack: list[object] = [None]

    def tile(path: str) -> bytes | None:
        found = cache_pack.file(path)
        return found.read_bytes() if found else None

    def ground_m() -> float | None:
        """This Node's ground height above the coast datum, from its pack's terrain."""
        if not isinstance(region.water, Coast):
            return None
        if ground_heights_pack[0] is not cache_pack.manifest:
            ground_heights.clear()
            ground_heights_pack[0] = cache_pack.manifest
        spot = Position(settings.latitude, settings.longitude)
        if spot not in ground_heights:
            try:
                ground_heights[spot] = elevation_at(tile, spot.latitude, spot.longitude)
            except (ValueError, OSError, zlib.error, struct.error) as error:
                # Until a pack with readable terrain arrives, the Node reads its spot as dry.
                logger.warning("no ground height at %s (%s); reading the spot as dry", spot, error)
                ground_heights[spot] = None
        return ground_heights[spot]

    def own_measurements() -> list[Reading] | None:
        """What this Node reads from the Event's surface at its own position.

        With the Event clock stopped, or running an Event this Node does not hold, it reads the
        first moment of its first Event.
        """
        heard = event_clock.current(clock())
        event = clocked_event()
        if heard.state == "stopped" or heard.event not in events:
            event_t = event.start_unix
        else:
            event_t = heard.event_t
        spot = SensorSpot(
            Position(settings.latitude, settings.longitude), settings.river_km, ground_m()
        )
        readings = event.readings_at(spot, event_t, clock())
        return [r for r in readings if r.kind in measured_kinds] or None

    def keep_reading(sender: str, reading: CommunityReading) -> None:
        store.record(sender, reading, clock())
        stop_replay_if_live()
        warn_about_new_triggers()

    def hear_community_reading(sender: str, message: Message) -> None:
        if isinstance(message, CommunityReading):
            keep_reading(sender, message)

    publisher = ReadingPublisher(
        mesh,
        lambda: fuzz_position(settings.latitude, settings.longitude),
        lambda: settings.river_km,
        own_measurements,
        keep_reading,
    )

    heard_warnings = HeardCommunityWarnings()
    hub_warnings = HubWarnings(int(clock().timestamp())) if settings.role == "hub" else None
    flood_email = FloodEmail.from_settings(settings, region)

    def hear_community_warning(_: str, message: Message) -> None:
        if isinstance(message, CommunityWarning):
            heard_warnings.hear(message)

    def repeat_community_warnings() -> None:
        if hub_warnings:
            for warning in hub_warnings.sent():
                mesh.publish(warning)

    def warn_about_new_triggers() -> None:
        """Hub only: warn about each Registered Node whose Hazard trigger has not been warned about."""
        if not hub_warnings:
            return
        registered_ids = heard_registry.registered_ids()
        snapshot = store.snapshot(clock())
        live = snapshot.is_live(registered_ids)
        triggers = warning_triggers(
            snapshot.as_seen_by(registered_ids).recent, registered_ids, rules
        )
        event = event_clock.current(clock())
        now = int(clock().timestamp())
        # With no replay running the trigger fired now, on the Hub's own clock.
        surge_t = now if event.state == "stopped" else event.event_t
        speedup = event.rate if event.state == "playing" else 1
        for warning in hub_warnings.issue_for_new_triggers(
            region.hazard, triggers, surge_t, now, speedup
        ):
            # The Hub does not hear its own broadcasts, so it keeps the warning itself.
            heard_warnings.hear(warning)
            # A measured speed updates a warning the team was already emailed about.
            # A Live Hub only warns from real readings, so its email is never a rehearsal.
            if flood_email and warning.measured is None:
                flood_email.send_for(warning, rehearsal=event.state != "stopped" and not live)
            try:
                mesh.publish(warning)
            except Exception:
                # The Hub already shows it and has it in its log.
                logger.exception("could not send Community Warning %s", warning.id)

    shelter_status = HeardShelterStatus()

    def hear_shelter_status(_: str, message: Message) -> None:
        if isinstance(message, ShelterStatus):
            shelter_status.hear(message)

    shelter_registry = ShelterRegistry(
        cache_pack.shelter_ids,
        lambda: int(clock().timestamp()),
        settings.data_dir / "shelter_status.json",
    )

    def announce_shelters(status: ShelterStatus) -> None:
        # The Hub does not hear its own broadcasts, so it takes the status itself.
        shelter_status.hear(status)
        try:
            mesh.publish(status)
        except Exception:
            # The change already stands on the Hub, and the next repeat sends it again.
            logger.exception("could not announce the Shelter status")

    def repeat_shelter_status() -> None:
        status = shelter_registry.snapshot()
        if status:
            announce_shelters(status)

    official_gauges = HeardOfficialGauges(region.official_gauges)

    def hear_official_gauge(_: str, message: Message) -> None:
        if isinstance(message, OfficialGaugeLevel):
            official_gauges.hear(message)

    def announce_gauge_level(level: OfficialGaugeLevel) -> None:
        # The Hub does not hear its own broadcasts, so it keeps the level itself.
        official_gauges.hear(level)
        try:
            mesh.publish(level)
        except Exception:
            # The Hub already shows it, and the next repeat sends it again.
            logger.exception("could not announce the level of NOAA station %s", level.station)

    def poll_official_gauges() -> None:
        """Ask NOAA for every gauge's latest level; one station failing leaves the others."""
        for gauge in region.official_gauges:
            try:
                level = read_noaa_level(gauge_source, gauge)
            except httpx.HTTPError as error:
                logger.warning("could not read NOAA station %s: %s", gauge.station, error)
                continue
            if level:
                announce_gauge_level(level)

    def repeat_official_gauges() -> None:
        for level in official_gauges.all_newest():
            announce_gauge_level(level)

    heard_registry = HeardRegistry()
    sign_up_pressed = threading.Event()

    def hear_registry(_: str, message: Message) -> None:
        if isinstance(message, NodeRegistryMessage):
            heard_registry.hear(message)

    def registration() -> RegistrationState:
        if settings.role == "hub" or mesh.identity in heard_registry.registered_ids():
            return "registered"
        return "waiting" if sign_up_pressed.is_set() else "unverified"

    def send_sign_up() -> None:
        try:
            mesh.publish(SignUp(node=mesh.identity, name=settings.name[:NODE_NAME_MAX_LENGTH]))
        except Exception:
            # Nothing is lost: the next repeat sends it again.
            logger.exception("could not send the Sign-up")

    def repeat_sign_up() -> None:
        if sign_up_pressed.is_set() and registration() != "registered":
            send_sign_up()

    hub_registry = (
        HubRegistry(
            RegisteredNode(id=mesh.identity, name=settings.name),
            lambda: int(clock().timestamp()),
            settings.data_dir / "registry.json",
        )
        if settings.role == "hub"
        else None
    )

    def hear_sign_up(_: str, message: Message) -> None:
        if hub_registry and isinstance(message, SignUp):
            hub_registry.hear_sign_up(message, clock())

    def announce_registry(registry: NodeRegistryMessage) -> None:
        # The Hub does not hear its own broadcasts, so it takes the registry itself.
        heard_registry.hear(registry)
        try:
            mesh.publish(registry)
        except Exception:
            # The change already stands on the Hub, and the next repeat sends it again.
            logger.exception("could not announce the Node registry")

    def repeat_registry() -> None:
        if hub_registry:
            announce_registry(hub_registry.snapshot())

    def hear_event_clock(_: str, message: Message) -> None:
        if isinstance(message, ReplayClockMessage) and message.event in events:
            event_clock.hear(message, clock())

    def announce_event_clock(message: ReplayClockMessage) -> None:
        # The Hub does not hear its own broadcasts, so it sets its own clock too.
        event_clock.hear(message, clock())
        try:
            mesh.publish(message)
        except Exception:
            # The clock already runs on the Hub, and the next repeat sends it again.
            logger.exception("could not announce the Event clock")

    official_alerts = HeardOfficialAlerts()

    def hear_official_alert(_: str, message: Message) -> None:
        if isinstance(message, OfficialAlert):
            official_alerts.hear(message)

    forwarded_alert_ids: set[str] = set()

    def due_official_alerts() -> list[OfficialAlert]:
        event = event_clock.current(clock())
        return (
            [] if event.state == "stopped" else clocked_event().official_alerts_due(event.event_t)
        )

    def forward_official_alert(alert: OfficialAlert) -> None:
        # The Hub does not hear its own broadcasts, so it keeps the alert itself.
        official_alerts.hear(alert)
        forwarded_alert_ids.add(alert.id)
        try:
            mesh.publish(alert)
        except Exception:
            # The Hub already shows it, and the next repeat sends it again.
            logger.exception("could not forward Official Alert %s", alert.id)

    def forward_newly_due_official_alerts() -> None:
        for alert in due_official_alerts():
            if alert.id not in forwarded_alert_ids:
                forward_official_alert(alert)

    def hub_is_live() -> bool:
        return store.snapshot(clock()).is_live(heard_registry.registered_ids())

    def stop_replay_if_live() -> None:
        """Hub only: real Sensors are reporting, so no Replay may run (paused counts as running)."""
        if settings.role != "hub" or event_clock.current(clock()).state == "stopped":
            return
        if hub_is_live():
            running = event_clock.current(clock())
            announce_event_clock(
                ReplayClockMessage(
                    event=running.event, state="stopped", event_t=running.event_t, rate=running.rate
                )
            )

    def pause_at_the_end() -> None:
        """Hold the clock at the replay's end instead of letting it play on past the Event's end."""
        event = event_clock.current(clock())
        ending = clocked_event()
        if event.state == "playing" and event.event_t >= ending.end_unix:
            announce_event_clock(
                ReplayClockMessage(
                    event=ending.id,
                    state="paused",
                    event_t=ending.end_unix,
                    rate=event.rate,
                )
            )

    def repeat_due_official_alerts() -> None:
        for alert in due_official_alerts():
            forward_official_alert(alert)

    mesh.subscribe(hear_community_reading)
    if settings.role == "sensor":
        # The Hub is the only source of the clock, so it never takes one from the Mesh.
        mesh.subscribe(hear_event_clock)
    mesh.subscribe(hear_official_alert)
    mesh.subscribe(hear_community_warning)
    mesh.subscribe(hear_official_gauge)
    mesh.subscribe(hear_shelter_status)
    mesh.subscribe(hear_registry)
    mesh.subscribe(hear_sign_up)
    publisher.share()
    if settings.role == "hub":
        repeat_shelter_status()
        repeat_registry()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def keep_sharing() -> None:
            while True:
                playing = event_clock.current(clock()).state != "stopped"
                await asyncio.sleep(
                    min(settings.publish_every_seconds, REPLAY_PUBLISH_EVERY_SECONDS)
                    if playing
                    else settings.publish_every_seconds
                )
                try:
                    publisher.share()
                except Exception:
                    # One bad tick must not silence this Node for the rest of the storm.
                    logger.exception("could not share this Node's readings")

        async def fetch_cache_pack() -> None:
            while cache_pack.manifest is None:
                try:
                    await asyncio.to_thread(
                        cache_pack.download, settings.cache_pack_url, pack_source
                    )
                except Exception:
                    # Whatever went wrong, a Node without a pack must keep retrying.
                    logger.exception("could not get the Cache Pack, retrying")
                    await asyncio.sleep(RETRY_EVERY_SECONDS)

        async def keep_weather_forecast_fresh() -> None:
            while True:
                try:
                    if settings.role == "hub":
                        await asyncio.to_thread(weather_forecast.fetch, weather_source, clock())
                    else:
                        await asyncio.to_thread(
                            weather_forecast.download, settings.weather_forecast_url, weather_source
                        )
                except httpx.HTTPError as error:
                    # Offline or rate-limited is routine, and the error text carries the URL.
                    logger.warning(
                        "could not refresh the weather forecast: %s", type(error).__name__
                    )
                except Exception:
                    # The copy on disk stays; the layers say how old it is.
                    logger.exception("could not refresh the weather forecast")
                # Without any copy a Node retries soon: the Hub may not have fetched yet.
                has_copy = weather_forecast.read() is not None
                await asyncio.sleep(
                    settings.weather_forecast_seconds if has_copy else RETRY_EVERY_SECONDS
                )

        async def keep_checking_internet() -> None:
            while True:
                try:
                    await asyncio.to_thread(internet.probe)
                except Exception:
                    logger.exception("could not check whether this Node has internet")
                await asyncio.sleep(settings.internet_check_seconds)

        # Also how a Hub whose pack arrives late starts announcing; it waits at most one period.
        async def keep_repeating_shelter_status() -> None:
            while True:
                await asyncio.sleep(settings.shelter_repeat_seconds)
                try:
                    repeat_shelter_status()
                except Exception:
                    logger.exception("could not repeat the Shelter status")

        async def keep_polling_official_gauges() -> None:
            while True:
                online = False
                try:
                    # Offline there is nothing to ask; the Mesh keeps the last level meanwhile.
                    online = internet.status == "online"
                    if online:
                        await asyncio.to_thread(poll_official_gauges)
                except Exception:
                    logger.exception("could not poll the Official Gauges")
                # Until the first connectivity check lands the status reads "mesh_only", so look
                # again at the next check rather than leaving a fresh Hub without a level for a poll.
                await asyncio.sleep(
                    settings.gauge_poll_seconds
                    if online
                    else min(settings.gauge_poll_seconds, settings.internet_check_seconds)
                )

        async def keep_repeating_official_gauges() -> None:
            while True:
                await asyncio.sleep(settings.gauge_repeat_seconds)
                try:
                    repeat_official_gauges()
                except Exception:
                    logger.exception("could not repeat the Official Gauges")

        async def keep_repeating_registry() -> None:
            while True:
                await asyncio.sleep(settings.registry_repeat_seconds)
                try:
                    repeat_registry()
                except Exception:
                    logger.exception("could not repeat the Node registry")

        async def keep_repeating_warnings() -> None:
            while True:
                await asyncio.sleep(settings.warning_repeat_seconds)
                try:
                    repeat_community_warnings()
                except Exception:
                    logger.exception("could not repeat the Community Warnings")

        async def keep_signing_up() -> None:
            while True:
                await asyncio.sleep(settings.sign_up_repeat_seconds)
                try:
                    repeat_sign_up()
                except Exception:
                    logger.exception("could not repeat the Sign-up")

        async def keep_repeating_event_clock() -> None:
            while True:
                await asyncio.sleep(settings.replay_repeat_seconds)
                try:
                    event = event_clock.current(clock())
                    if event.state != "stopped":
                        announce_event_clock(event)
                        # A Node that joined late or missed a packet gets the alerts with the clock.
                        repeat_due_official_alerts()
                except Exception:
                    logger.exception("could not repeat the Event clock")

        async def keep_following_the_timeline() -> None:
            while True:
                await asyncio.sleep(settings.alert_check_seconds)
                try:
                    # Alerts first, so the last one is sent before the clock stops at the end.
                    forward_newly_due_official_alerts()
                    pause_at_the_end()
                except Exception:
                    logger.exception("could not follow the Event")

        tasks = [
            asyncio.create_task(keep_sharing()),
            asyncio.create_task(keep_checking_internet()),
            asyncio.create_task(keep_signing_up()),
        ]
        if settings.role == "hub":
            tasks.append(asyncio.create_task(keep_repeating_shelter_status()))
            tasks.append(asyncio.create_task(keep_polling_official_gauges()))
            tasks.append(asyncio.create_task(keep_repeating_official_gauges()))
            tasks.append(asyncio.create_task(keep_repeating_registry()))
            tasks.append(asyncio.create_task(keep_repeating_warnings()))
            tasks.append(asyncio.create_task(keep_repeating_event_clock()))
            tasks.append(asyncio.create_task(keep_following_the_timeline()))
        if settings.cache_pack_url:
            tasks.append(asyncio.create_task(fetch_cache_pack()))
        if settings.role == "hub" or settings.weather_forecast_url:
            tasks.append(asyncio.create_task(keep_weather_forecast_fresh()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()

    app = FastAPI(title="Storm Shield Node", lifespan=lifespan)
    # So the Sandbox, which moves a Node, can have it read from its new spot at once.
    app.state.share_reading = publisher.share

    @app.get("/api/state")
    def node_state() -> NodeState:
        registered_ids = heard_registry.registered_ids()
        full_snapshot = store.snapshot(clock())
        snapshot = full_snapshot.as_seen_by(registered_ids)
        return NodeState(
            id=mesh.identity,
            name=settings.name,
            role=settings.role,
            status=internet.status,
            registration=registration(),
            sandbox=SandboxState() if sandbox else None,
            region=region.summary(),
            hazard=region.hazard,
            live=full_snapshot.is_live(registered_ids),
            flood_risk=flood_risk(snapshot.recent, registered_ids, rules),
            nodes=[
                NodeEntry(
                    **node.model_dump(),
                    registered=node.id in registered_ids,
                    name=heard_registry.name_of(node.id),
                )
                for node in snapshot.nodes
            ],
            official_alerts=official_alerts.shown_at(event_clock.current(clock())),
            community_warnings=heard_warnings.shown_at(event_clock.current(clock())),
            official_gauges=[
                _gauge_state(gauge, official_gauges.newest(gauge))
                for gauge in region.official_gauges
            ],
        )

    @app.post("/api/registry/signup")
    def sign_up_with_hub() -> dict[str, RegistrationState]:
        # The press is kept in memory only: after a restart an unregistered Node starts over.
        if registration() == "unverified":
            sign_up_pressed.set()
            send_sign_up()
        return {"registration": registration()}

    @app.get("/api/replay")
    def replay_clock() -> ReplayClockMessage:
        return event_clock.current(clock())

    @app.get("/api/replay/events")
    def replay_events() -> ReplayEvents:
        return ReplayEvents(
            events=[ReplayEventSummary(id=event.id, label=event.label) for event in events.values()]
        )

    @app.get("/api/replay/phases")
    def replay_phases(event: str | None = None) -> ReplayPhases:
        shown = clocked_event() if event is None else events.get(event)
        if shown is None:
            raise HTTPException(status_code=404, detail=f"unknown Event {event!r}")
        return ReplayPhases(
            phases=[
                ReplayPhase(id=phase.id, label=phase.label, event_t=shown.event_t_at(phase.at))
                for phase in shown.phases
            ],
            internet_cue_event_t=shown.event_t_at(shown.internet_cue.at),
        )

    @app.get("/api/cache-pack")
    def cache_pack_status() -> CachePackStatus:
        manifest = cache_pack.manifest
        return CachePackStatus(available=manifest is not None, manifest=manifest)

    @app.get("/api/cache-pack.zip")
    def cache_pack_zip() -> FileResponse:
        if cache_pack.manifest is None:
            raise HTTPException(status_code=404, detail="no Cache Pack on this Node yet")
        return FileResponse(cache_pack.zip_path, media_type="application/zip")

    @app.get("/api/cache-pack/files/{path:path}")
    def cache_pack_file(path: str) -> FileResponse:
        file = cache_pack.file(path)
        if file is None:
            raise HTTPException(status_code=404, detail="not in the Cache Pack")
        return FileResponse(file)

    @app.get("/api/weather/replay")
    def weather_replay() -> FileResponse:
        file = cache_pack.file("weather_replay.json")
        if file is None:
            raise HTTPException(
                status_code=404, detail="no recorded weather in this Node's Cache Pack"
            )
        return FileResponse(file, media_type="application/json")

    @app.get("/api/weather/forecast")
    def weather_forecast_file() -> Response:
        forecast = weather_forecast.read()
        if forecast is None:
            raise HTTPException(status_code=404, detail="no weather forecast on this Node yet")
        return Response(forecast, media_type="application/json")

    @app.get("/api/shelters")
    def open_shelters() -> OpenShelters:
        # Nothing counts as open until the Hub says so; an id this Node's pack lacks is ignored.
        return OpenShelters(open=shelter_status.open_among(cache_pack.shelter_ids()))

    if settings.role == "hub":

        @app.post("/api/shelters/open")
        def set_shelter_open(change: ShelterChange) -> OpenShelters:
            if not cache_pack.shelter_ids():
                raise HTTPException(
                    status_code=503, detail="the Hub has no valid Cache Pack, so no Shelters yet"
                )
            try:
                status = shelter_registry.set_open(change.id, change.open)
            except UnknownShelter:
                raise HTTPException(
                    status_code=422, detail=f"unknown Shelter {change.id!r}"
                ) from None
            announce_shelters(status)
            return OpenShelters(open=status.open)

    if not hub_registry:
        # Not defined, these would fall through to the dashboard's static mount and answer 405.
        @app.get("/api/registry")
        @app.post("/api/registry/accept")
        @app.get("/api/warnings")
        def not_on_a_sensor() -> None:
            raise HTTPException(status_code=404, detail="only the Hub keeps the registry and log")

    if hub_warnings:

        @app.get("/api/warnings")
        def warning_log() -> WarningLog:
            return WarningLog(warnings=hub_warnings.sent())

    if hub_registry:

        @app.get("/api/registry")
        def registry_summary() -> RegistrySummary:
            now = clock()
            heard = {node.id: node.age_s for node in store.snapshot(now).nodes}
            return hub_registry.summary(heard, now)

        @app.post("/api/registry/accept")
        def accept_sign_up(accept: RegistryAccept) -> RegistrySummary:
            try:
                registry = hub_registry.accept(accept.id)
            except NoWaitingSignUp:
                raise HTTPException(
                    status_code=404, detail=f"no Sign-up from Node {accept.id!r} is waiting"
                ) from None
            except RegistryFull:
                raise HTTPException(
                    status_code=409,
                    detail="the registry would no longer fit one packet; nothing was accepted",
                ) from None
            announce_registry(registry)
            return registry_summary()

    if settings.role == "hub":
        chosen_rate = first_event.rate
        # These endpoints run on the threadpool: a rate change racing a Start must not announce
        # the old rate.
        replay_lock = threading.RLock()

        def set_replay(
            event: Event, state: Literal["playing", "paused"], event_t: int
        ) -> ReplayClockMessage:
            with replay_lock:
                announce_event_clock(
                    ReplayClockMessage(
                        event=event.id, state=state, event_t=event_t, rate=chosen_rate
                    )
                )
                return event_clock.current(clock())

        @app.post("/api/replay/rate")
        def set_replay_rate(change: ReplayRate) -> ReplayClockMessage:
            nonlocal chosen_rate
            with replay_lock:
                chosen_rate = change.rate
                heard = event_clock.current(clock())
                if heard.state == "stopped":
                    return heard
                return set_replay(clocked_event(), heard.state, heard.event_t)

        def picked_or_clocked(picked: str | None) -> Event:
            """The Event a control names, else the one on the clock."""
            event = clocked_event() if picked is None else events.get(picked)
            if event is None:
                raise HTTPException(status_code=422, detail=f"unknown Event {picked!r}")
            return event

        def refuse_while_live() -> None:
            if hub_is_live():
                raise HTTPException(
                    status_code=409, detail="live Sensors are reporting, so no Replay can play"
                )

        @app.post("/api/replay/start")
        def start_replay(start: ReplayStart | None = None) -> ReplayClockMessage:
            refuse_while_live()
            event = picked_or_clocked(start.event if start else None)
            return set_replay(event, "playing", event.start_unix)

        @app.post("/api/replay/pause")
        def pause_replay() -> ReplayClockMessage:
            heard = event_clock.current(clock())
            if heard.state != "playing":
                raise HTTPException(status_code=409, detail="the replay is not playing")
            return set_replay(clocked_event(), "paused", heard.event_t)

        @app.post("/api/replay/resume")
        def resume_replay() -> ReplayClockMessage:
            refuse_while_live()
            heard = event_clock.current(clock())
            if heard.state != "paused":
                raise HTTPException(status_code=409, detail="the replay is not paused")
            event = clocked_event()
            if heard.event_t >= event.end_unix:
                raise HTTPException(
                    status_code=409, detail="the replay has ended; Reset or jump to a phase"
                )
            return set_replay(event, "playing", heard.event_t)

        @app.post("/api/replay/reset")
        def reset_replay(reset: ReplayStart | None = None) -> ReplayClockMessage:
            refuse_while_live()
            # Paused at 08:30 rather than stopped, so every Node keeps following the Event clock.
            event = picked_or_clocked(reset.event if reset else None)
            return set_replay(event, "paused", event.start_unix)

        @app.post("/api/replay/jump")
        def jump_replay(jump: ReplayJump) -> ReplayClockMessage:
            refuse_while_live()
            event = picked_or_clocked(jump.event)
            phase = next((p for p in event.phases if p.id == jump.phase), None)
            if phase is None:
                raise HTTPException(status_code=422, detail=f"unknown phase {jump.phase!r}")
            keeps_paused = event_clock.current(clock()).state == "paused"
            return set_replay(
                event, "paused" if keeps_paused else "playing", event.event_t_at(phase.at)
            )

    if sandbox is not None:

        @app.get("/api/sandbox/nodes")
        def sandbox_nodes() -> SandboxNodes:
            return sandbox.nodes()

        @app.post("/api/sandbox/radio-range")
        def set_sandbox_radio_range(change: RadioRange) -> SandboxNodes:
            return sandbox.set_radio_range(change.radio_range_m)

        @app.post("/api/sandbox/sensors")
        def add_sandbox_sensor(spot: Spot) -> SandboxNodes:
            try:
                return sandbox.add_sensor(spot)
            except SandboxRefused as refusal:
                raise HTTPException(status_code=409, detail=str(refusal)) from None

        @app.put("/api/sandbox/sensors/{sensor_id}")
        def move_sandbox_sensor(sensor_id: str, spot: Spot) -> SandboxNodes:
            try:
                return sandbox.move_sensor(sensor_id, spot)
            except UnknownSensor:
                raise HTTPException(status_code=404, detail=f"no Sensor {sensor_id!r}") from None
            except SandboxRefused as refusal:
                raise HTTPException(status_code=409, detail=str(refusal)) from None

        @app.delete("/api/sandbox/sensors/{sensor_id}")
        def remove_sandbox_sensor(sensor_id: str) -> SandboxNodes:
            try:
                return sandbox.remove_sensor(sensor_id)
            except UnknownSensor:
                raise HTTPException(status_code=404, detail=f"no Sensor {sensor_id!r}") from None

    @app.get("/api/join")
    def hotspot_to_join(request: Request) -> dict[str, str]:
        # The password is a secret, so only the person at this machine (the projected Hub) gets it.
        if request.client is None or request.client.host not in LOOPBACK_HOSTS:
            raise HTTPException(status_code=403, detail="only this Node's own machine may ask")
        if not settings.hotspot_ssid:
            raise HTTPException(status_code=404, detail="HOTSPOT_SSID is not set on this Node")
        return {
            "ssid": settings.hotspot_ssid,
            "password": settings.hotspot_password,
            "url": settings.dashboard_url,
        }

    @app.get("/api/tiles/{z}/{x}/{y}.png")
    def map_tile(z: int, x: int, y: int) -> Response:
        if not settings.carto_api_key:
            raise HTTPException(status_code=404, detail="CARTO_API_KEY is not set on this Node")
        try:
            upstream = tile_source.get(
                CARTO_TILE_URL.format(z=z, x=x, y=y), params={"key": settings.carto_api_key}
            )
        except httpx.HTTPError as error:
            # The error text can carry the request URL, and the URL carries the key.
            logger.warning("CARTO tile request failed: %s", type(error).__name__)
            raise HTTPException(status_code=502, detail="CARTO is unreachable") from None
        if upstream.status_code != 200:
            raise HTTPException(status_code=502, detail=f"CARTO answered {upstream.status_code}")
        return Response(
            upstream.content,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Mounted last so it never shadows /api routes.
    dashboard = settings.dashboard_dir
    if dashboard.is_dir():
        app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")
    return app


def build_mesh(settings: Settings) -> Mesh:
    if settings.mesh == "memory":
        return InMemoryNetwork().join(settings.name, settings.hub_identity)
    return ReticulumMesh(settings)


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    # Only a running Node looks for the Release; tests build their Nodes with create_app and
    # never download.
    settings.cache_pack_url = download_source(settings.cache_pack_url, settings.region)
    mesh = build_mesh(settings)
    logger.info("Node %s (%s) is up as %s", mesh.identity, settings.name, settings.role)
    uvicorn.run(create_app(settings, mesh), host="0.0.0.0", port=settings.port)
