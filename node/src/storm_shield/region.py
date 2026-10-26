import json
from pathlib import Path
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# Resolved from this file, not the cwd, so the Node starts from any directory.
REGIONS_DIR = Path(__file__).resolve().parents[3] / "regions"

Hazard = Literal["flash_flood", "storm_surge"]

# An Official Alert's source tag travels in every alert, which must fit one 464-byte packet.
ALERT_TAG_MAX_LENGTH = 16

LatLon = Annotated[tuple[float, float], Field(description="latitude, longitude")]


class RegionError(Exception):
    """A Region file the Node cannot use; the message names the file and each bad field."""


class _Strict(BaseModel):
    # A misspelt field is an error, not a threshold that silently keeps its default.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Length(_Strict):
    value: float
    unit: Literal["cm", "m", "ft"]

    @property
    def cm(self) -> float:
        return self.value * {"cm": 1.0, "m": 100.0, "ft": 30.48}[self.unit]


class RainRate(_Strict):
    value: float
    unit: Literal["mm/h", "in/h"]

    @property
    def mm_per_hour(self) -> float:
        return self.value * {"mm/h": 1.0, "in/h": 25.4}[self.unit]


class Pressure(_Strict):
    value: float
    unit: Literal["hPa", "inHg"]

    @property
    def hpa(self) -> float:
        return self.value * {"hPa": 1.0, "inHg": 33.8639}[self.unit]


class FlashFlood(_Strict):
    """The thresholds of a river Region's flash flood, each written in the Region's own units."""

    surge_rise: Length
    surge_window_s: int = Field(gt=0)
    elevated_level: Length
    high_level: Length
    rising: Length
    # How much history Flood Risk keeps; `rising` is the gain across it.
    rising_window_s: int = Field(gt=0)

    @model_validator(mode="after")
    def _surge_fits_in_the_history(self) -> Self:
        if self.surge_window_s > self.rising_window_s:
            raise ValueError("surge_window_s cannot be longer than rising_window_s")
        return self


class StormSurge(_Strict):
    """The thresholds of a coast Region's storm surge, each written in the Region's own units.

    Levels are the water surface's height above the Region's datum.
    """

    # A Registered Node's level passing this while it has risen `rising` is a Community Warning.
    warning_height: Length
    rising: Length
    # How much history Flood Risk keeps; `rising` is the gain across it.
    rising_window_s: int = Field(gt=0)
    elevated_level: Length
    high_level: Length


class FloodWarningRules(_Strict):
    """What the flood-warning Rule set reads from a river Region."""

    flash_flood: FlashFlood
    rain_elevated: RainRate
    rain_high: RainRate
    storm_pressure: Pressure
    soil_rising_points: float = Field(gt=0)

    @property
    def water_levels(self) -> FlashFlood:
        """The Hazard's thresholds, whose levels and rise every Hazard has."""
        return self.flash_flood


class CoastFloodWarningRules(_Strict):
    """What the flood-warning Rule set reads from a coast Region."""

    storm_surge: StormSurge
    rain_elevated: RainRate
    rain_high: RainRate
    storm_pressure: Pressure
    soil_rising_points: float = Field(gt=0)

    @property
    def water_levels(self) -> StormSurge:
        """The Hazard's thresholds, whose levels and rise every Hazard has."""
        return self.storm_surge


FloodWarning = FloodWarningRules | CoastFloodWarningRules


class Rules(_Strict):
    flood_warning: FloodWarning


class DisplayUnits(_Strict):
    """The units residents read; numbers are converted on screen only."""

    water_level: Literal["cm", "m", "ft"]
    rain_rate: Literal["mm/h", "in/h"]
    soil_moisture: Literal["%"]
    air_pressure: Literal["hPa", "inHg"]
    distance: Literal["km", "mi"]


class AlertSource(_Strict):
    """An authority whose Official Alerts this Region shows, credited by `name`."""

    tag: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=ALERT_TAG_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=40)
    covers: str = Field(min_length=1)


class River(_Strict):
    type: Literal["river"]
    # Where River km is zero (latitude, longitude); km is negative upstream of it.
    km_origin: LatLon
    # Files under the Region's folder.
    line_source: str
    corridor_source: str


class Coast(_Strict):
    type: Literal["coast"]
    # Water levels, ground heights and gauges all compare in this datum.
    datum: Literal["NAVD88"]
    # The build traces the Flood-Prone Area as the land below this height.
    flood_prone_below: Length


class Shelter(_Strict):
    id: str
    name: str
    pos: LatLon
    # Set when the Region's water is a river; a coast Shelter's safety is its height, not this.
    height_above_river_m: float | None = None
    special_needs: bool
    pet_friendly: bool
    source: str


class HighGroundPoint(_Strict):
    id: str
    name: str
    pos: LatLon
    town: str
    # Where the walk to the point starts: the town's centre.
    town_pos: LatLon
    source: str
    checked: str


class SensorSite(_Strict):
    id: str
    label: str
    pos: LatLon
    # Set when the Region's water is a river.
    river_km: float | None = None
    why: str


class OfficialGauge(_Strict):
    """A tide gauge the Hub brings into the Mesh as an Official Gauge."""

    agency: Literal["NOAA"]
    station: str
    label: str
    pos: LatLon
    # Added to the station's published level (its own datum) to give the height in the Region's.
    datum_offset: Length


class Source(_Strict):
    # An http(s) address, or a path under the Region's folder for a local copy (what tests use).
    url: str = Field(min_length=1)
    credit: str = Field(min_length=1)


class Sources(_Strict):
    """Where the Cache Pack build gets the Region's map and weather."""

    # A Terrarium tile address with {z}, {x} and {y}.
    terrain: Source
    # An OpenStreetMap extract (.pbf) of the country or state around the bbox.
    roads: Source
    # An Overpass API endpoint, or a saved Overpass answer.
    basemap: Source
    # Open-Meteo's archive endpoint, or a saved answer.
    weather: Source


class Region(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    label: str
    # south, west, north, east
    bbox: tuple[float, float, float, float]
    time_zone: str
    display_units: DisplayUnits
    official_alert_sources: list[AlertSource] = Field(min_length=1)
    water: River | Coast = Field(discriminator="type")
    rules: Rules
    shelters: list[Shelter]
    high_ground: list[HighGroundPoint] = []
    sensor_sites: list[SensorSite]
    # Where the Region's Hub runs; the Sandbox starts its Hub here.
    hub_site: SensorSite
    official_gauges: list[OfficialGauge] = []
    sources: Sources

    @field_validator("bbox")
    @classmethod
    def _bbox_is_a_box(
        cls, bbox: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        south, west, north, east = bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("must be south, west, north, east with south < north and west < east")
        return bbox

    @field_validator("time_zone")
    @classmethod
    def _time_zone_exists(cls, name: str) -> str:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"{name!r} is not an IANA time zone") from error
        return name

    @model_validator(mode="after")
    def _everything_lies_in_the_box(self) -> Self:
        south, west, north, east = self.bbox
        places = [
            *((f"shelters[{i}]", each.pos) for i, each in enumerate(self.shelters)),
            *((f"high_ground[{i}]", each.pos) for i, each in enumerate(self.high_ground)),
            *(
                (f"high_ground[{i}].town_pos", each.town_pos)
                for i, each in enumerate(self.high_ground)
            ),
            *((f"sensor_sites[{i}]", each.pos) for i, each in enumerate(self.sensor_sites)),
            ("hub_site", self.hub_site.pos),
            *((f"official_gauges[{i}]", each.pos) for i, each in enumerate(self.official_gauges)),
        ]
        outside = [
            where
            for where, (lat, lon) in places
            if not (south <= lat <= north and west <= lon <= east)
        ]
        if outside:
            raise ValueError(f"outside the Region's bbox: {', '.join(outside)}")
        return self

    @model_validator(mode="after")
    def _the_water_fits_its_rules_and_shelters(self) -> Self:
        river = isinstance(self.water, River)
        if river != isinstance(self.rules.flood_warning, FloodWarningRules):
            wanted = "flash_flood" if river else "storm_surge"
            raise ValueError(f"a {self.water.type} Region's flood_warning rules need {wanted}")
        if river and any(each.height_above_river_m is None for each in self.shelters):
            raise ValueError("every Shelter of a river Region needs height_above_river_m")
        if not river and any(each.height_above_river_m is not None for each in self.shelters):
            raise ValueError("a coast Region's Shelters have no height_above_river_m")
        if not river and self.high_ground:
            raise ValueError("high_ground measures its climb above a river, so a coast has none")
        return self

    @property
    def hazard(self) -> Hazard:
        """What the Region's water can do: a river means a flash flood, a coast a storm surge."""
        return "flash_flood" if isinstance(self.water, River) else "storm_surge"

    def _storm_surge_summary(self) -> "StormSurgeSummary | None":
        rules = self.rules.flood_warning
        if not isinstance(rules, CoastFloodWarningRules):
            return None
        surge = rules.storm_surge
        return StormSurgeSummary(
            rising_window_s=surge.rising_window_s,
            high_level_cm=surge.high_level.cm,
        )

    def has_alert_source(self, tag: str) -> bool:
        return any(source.tag == tag for source in self.official_alert_sources)

    def summary(self) -> "RegionSummary":
        return RegionSummary(
            name=self.name,
            label=self.label,
            water_type=self.water.type,
            storm_surge=self._storm_surge_summary(),
            time_zone=self.time_zone,
            display_units=self.display_units,
            official_alert_sources=self.official_alert_sources,
        )


class StormSurgeSummary(BaseModel):
    """The coast thresholds a Viewer needs to work out its own Water ETA, in centimetres."""

    rising_window_s: int
    high_level_cm: float


class RegionSummary(BaseModel):
    """What `/api/state` tells the dashboard about the Region."""

    name: str
    label: str
    water_type: Literal["river", "coast"]
    # Only a coast Region has one.
    storm_surge: StormSurgeSummary | None
    time_zone: str
    display_units: DisplayUnits
    official_alert_sources: list[AlertSource]


def load_region(path: Path) -> Region:
    """The Region in `path`; a file that does not fit the schema raises RegionError naming each
    bad field."""
    try:
        return Region.model_validate(json.loads(path.read_text()))
    except OSError as error:
        raise RegionError(f"cannot read Region file {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise RegionError(f"{path} is not JSON: {error}") from error
    except ValidationError as error:
        raise RegionError(f"{path}:\n{describe_problems(error)}") from error


def region_path(name: str) -> Path:
    return REGIONS_DIR / name / "region.json"


def events_dir(name: str) -> Path:
    """The Region's hand-written and built Event files, which the build and every Node read."""
    return REGIONS_DIR / name / "events"


def describe_problems(error: ValidationError) -> str:
    lines: list[str] = []
    for problem in error.errors():
        field = ".".join(str(part) for part in problem["loc"]) or "(whole file)"
        lines.append(f"  {field}: {problem['msg']}")
    return "\n".join(lines)
