from typing import Protocol

from pydantic import BaseModel, Field

from storm_shield.settings import Role


class SandboxNode(BaseModel):
    id: str
    name: str
    role: Role
    # The true spot the radio range is measured from; readings on the Mesh carry a fuzzed one.
    position: tuple[float, float]
    # The Nodes within radio range of this one: a line is drawn to each.
    links: list[str]
    # Radio hops to the Hub; null when no chain of Nodes reaches it.
    hops: int | None
    # Whether this Node has the newest Community Warning the Hub has sent.
    heard_warning: bool


class SandboxNodes(BaseModel):
    radio_range_m: float
    nodes: list[SandboxNode]


class RadioRange(BaseModel):
    radio_range_m: float = Field(gt=0)


class SandboxRegion(BaseModel):
    # The folder under regions/, which `--region` and the switch call take.
    name: str
    label: str


class SandboxRegions(BaseModel):
    current: str
    regions: list[SandboxRegion]


class RegionChoice(BaseModel):
    region: str


class Spot(BaseModel):
    """Where a Sensor goes: a place the user tapped or dropped it on the map."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class UnknownSensor(Exception):
    """No Sensor has this id; the Hub is not one, so it cannot be moved or removed."""


class SandboxRefused(Exception):
    """The Sandbox cannot do this; the message says why."""


class SandboxControls(Protocol):
    """What the Sandbox lets its Hub's dashboard see and change about the simulated Mesh."""

    def nodes(self) -> SandboxNodes: ...

    def set_radio_range(self, radio_range_m: float) -> SandboxNodes: ...

    def add_sensor(self, spot: Spot) -> SandboxNodes: ...

    def move_sensor(self, sensor_id: str, spot: Spot) -> SandboxNodes: ...

    def remove_sensor(self, sensor_id: str) -> SandboxNodes: ...

    def regions(self) -> SandboxRegions: ...

    def switch_region(self, region: str) -> SandboxRegions: ...
