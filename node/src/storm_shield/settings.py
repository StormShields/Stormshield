from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Role = Literal["sensor", "hub"]
MeshKind = Literal["reticulum", "memory"]
ReticulumInterface = Literal["auto", "loopback", "tcp"]

# The address pi/setup-hotspot.sh gives the machine that hosts the hotspot; a test keeps them equal.
HOTSPOT_ADDRESS = "10.88.0.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NODE_", populate_by_name=True)

    name: str = "node-1"
    # The folder under regions/ whose region.json this Node watches.
    region: str = "fort-myers"
    role: Role = "sensor"
    port: int = 8000
    # Betrawati until the operator sets the real spot; only a fuzzed copy leaves the Node.
    latitude: float = 27.9731
    longitude: float = 85.1860
    # Kilometres down the river from the Lhende-Kyirong confluence (negative above it); blank for a
    # Node that is not on the river, which then cannot start a Community Warning.
    river_km: float | None = None
    # Resolved from this file, not the cwd, so the Node starts from any directory.
    dashboard_dir: Path = Path(__file__).resolve().parents[3] / "dashboard" / "dist"
    # "memory" is a Node that hears only itself; tests and the dashboard dev server use it.
    mesh: MeshKind = "reticulum"
    # "auto" finds Nodes on the local Wi-Fi (the demo). "loopback" joins Nodes on this one machine,
    # for rehearsing without the Pis. "tcp" reaches Nodes at addresses you give it.
    mesh_interface: ReticulumInterface = "auto"
    # Each Node on one machine needs its own slot; only read when mesh_interface is "loopback".
    loopback_slot: int = 0
    # The lowest slot of this Node's group. A Node dials only the slots of its own group, so a
    # group started higher up (the demo, a test) never joins Nodes in slots below it.
    loopback_first_slot: int = 0
    # "tcp" is the fixed-address interface (for example over Tailscale): this Node listens on
    # tcp_port and dials every host in tcp_peers, a comma-separated list of "host" or "host:port".
    # Every Node must list every other Node, because Reticulum does not relay between clients.
    tcp_port: int = 4242
    tcp_peers: str = ""
    # The Hub of the one-laptop demo talks to S0 to S3 on loopback, and also to an Audience Node:
    # over Wi-Fi discovery, or over TCP when that laptop sits behind Docker's NAT. Off elsewhere.
    also_wifi_discovery: bool = False
    also_tcp_listen: bool = False
    # Holds this Node's Reticulum config and identity. Never shared between Nodes, never committed.
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    # How often this Node checks whether it has internet.
    internet_check_seconds: float = 5
    # How often the Hub repeats its Shelter status, so a Node that joined late or missed a packet
    # converges.
    shelter_repeat_seconds: float = 30
    # How often the Hub asks NOAA for each Official Gauge's latest level while it is online; NOAA
    # measures every 6 minutes.
    gauge_poll_seconds: float = 360
    # How often the Hub repeats the newest Official Gauge levels, so a Node that joined late or
    # missed a packet still has them after the internet goes down.
    gauge_repeat_seconds: float = 30
    # How often the Hub repeats the Node registry, so a Node that joined late or missed a packet
    # converges.
    registry_repeat_seconds: float = 30
    # How often a Node that pressed "Sign up" resends it until the Hub has accepted it.
    sign_up_repeat_seconds: float = 10
    # How often the Hub repeats the Event clock, so a Node that joined late or missed a packet
    # converges.
    replay_repeat_seconds: float = 10
    # How often the Hub sends every Community Warning again, so a Node that joined late or missed a
    # packet still gets it.
    warning_repeat_seconds: float = 10
    # How often the Hub checks whether the Event clock has reached a replayed Official Alert or
    # the end of the replay.
    alert_check_seconds: float = 1
    # How often a Node shares its readings.
    publish_every_seconds: float = 3
    # The kinds this Sensor Node measures, comma-separated; it sends only these. The default is the
    # four the flood-warning rules read. A kind with no source on this Node is simply never sent.
    measures: str = "water_level,rain_rate,soil_moisture,air_pressure"
    # Unprefixed on purpose: operators set CACHE_PACK_URL / CACHE_PACK_DIR in .env.
    # Empty URL means this Node never downloads a pack.
    cache_pack_url: str = Field(default="", validation_alias="CACHE_PACK_URL")
    # How often a Node refreshes its weather forecast: the Hub from Open-Meteo, others from the Hub.
    # Open-Meteo's free terms allow no more often than hourly.
    weather_forecast_seconds: float = 3600
    # Where a Sensor downloads the Hub's forecast, http://<hub>:8000/api/weather/forecast. Blank on
    # the Hub, which fetches it itself; a blank Sensor never gets a forecast.
    weather_forecast_url: str = ""
    # Secret: only this Node ever holds it; the dashboard asks the Node for tiles.
    carto_api_key: str = Field(default="", validation_alias="CARTO_API_KEY")
    # The hotspot a phone joins, read from the same .env lines as pi/setup-hotspot.sh. Only the
    # Node's own machine is told them (GET /api/join), for the Join card.
    hotspot_ssid: str = Field(default="", validation_alias="HOTSPOT_SSID")
    hotspot_password: str = Field(default="", validation_alias="HOTSPOT_PASSWORD")
    # Where a phone on the hotspot opens the dashboard; blank means the hotspot address of
    # pi/setup-hotspot.sh with this Node's port.
    hotspot_dashboard_url: str = Field(default="", validation_alias="HOTSPOT_DASHBOARD_URL")
    # The Hub emails the team on a new Community Warning when all three are set. Unprefixed like
    # CARTO_API_KEY, which also makes them the same operator-facing .env lines.
    alert_email_from: str = Field(default="", validation_alias="ALERT_EMAIL_FROM")
    # Secret: a Gmail app password, never the account password.
    alert_email_app_password: str = Field(default="", validation_alias="ALERT_EMAIL_APP_PASSWORD")
    # Comma-separated addresses.
    alert_email_to: str = Field(default="", validation_alias="ALERT_EMAIL_TO")
    cache_pack_dir: Path = Field(
        default=Path(__file__).resolve().parents[3] / "cache-pack",
        validation_alias="CACHE_PACK_DIR",
    )
    # Whose Shelter status this Node believes (the Hub prints its identity at startup). Blank or
    # wrong means no Shelter status is accepted, so the Node shows nothing open.
    hub_identity: str = Field(default="", validation_alias="HUB_IDENTITY")

    @property
    def dashboard_url(self) -> str:
        """Where a phone on the hotspot opens this Node's dashboard."""
        return self.hotspot_dashboard_url or f"http://{HOTSPOT_ADDRESS}:{self.port}"
