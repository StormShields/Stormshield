import { distanceInDisplayUnit, inDisplayUnit, speedInDisplayUnit } from "./displayUnits";
import type { DisplayUnits, Hazard, NodeSnapshot } from "./nodeState";

type CommunityWarningReason =
  "water_surge" | "water_high" | "water_rising" | "rain_heavy" | "pressure_falling";

// The wave's speed between the warning's origin and `node`, the next Node downstream to surge.
export type MeasuredSpeed = { node: string; km: number; surge_t: number; speed_kmh: number };

type WarningBase = {
  id: number;
  t: number;
  nodes: string[];
  reasons: CommunityWarningReason[];
  origin: string;
  // Event time the Hazard's trigger fired.
  surge_t: number;
};

// Fired by a Surge on a river, at the origin's River km.
export type FlashFloodWarning = WarningBase & {
  hazard: "flash_flood";
  origin_km: number;
  // Present once a second Node has surged downstream; the same warning, so not a new one.
  measured?: MeasuredSpeed | null;
};

// Fired by a coast level passing the warning height while rising; each Viewer works out its own
// Water ETA from the level and the rate (per hour of Event time).
export type StormSurgeWarning = WarningBase & {
  hazard: "storm_surge";
  origin_km: null;
  level_m: number | null;
  rise_m_per_h: number | null;
};

// A warning the Node has already checked against the Hub's signature; the browser cannot.
export type CommunityWarning = FlashFloodWarning | StormSurgeWarning;

// "Surge" alone would leave a resident guessing which water is coming.
const HAZARD_TITLES: Record<Hazard, string> = {
  flash_flood: "FLASH FLOOD",
  storm_surge: "STORM SURGE",
};

export function communityWarningTitle(warning: CommunityWarning): string {
  return `${HAZARD_TITLES[warning.hazard]} · COMMUNITY WARNING · NOT OFFICIAL`;
}

// The river map, wave and Wave ETA follow flash floods only.
export function flashFloodWarnings(warnings: CommunityWarning[]): FlashFloodWarning[] {
  return warnings.filter(
    (warning): warning is FlashFloodWarning => warning.hazard === "flash_flood",
  );
}

// Nepal's Department of Hydrology and Meteorology, the authority whose flood warnings count.
export const OFFICIAL_SOURCE = { name: "DHM Nepal", url: "https://www.hydrology.gov.np/" };

const REASON_SENTENCES: Record<CommunityWarningReason, string> = {
  water_surge: "Water is surging",
  water_high: "Water is high",
  water_rising: "Water is rising",
  rain_heavy: "Heavy rain",
  pressure_falling: "Pressure is falling",
};

export function reasonsSentence(warning: CommunityWarning): string {
  return warning.reasons.map((reason) => REASON_SENTENCES[reason]).join(", ");
}

export function firstSurgeAt(warnings: CommunityWarning[]): number | null {
  return warnings.length > 0 ? Math.min(...warnings.map((warning) => warning.surge_t)) : null;
}

// "Measured: 15.6 km in 12 min = 78 km/h (S0 to S1)"; null until a second Node has surged.
export function measuredSpeedLine(
  warning: CommunityWarning,
  nameOf: (nodeId: string) => string,
  units: DisplayUnits | null,
): string | null {
  if (warning.hazard !== "flash_flood" || !warning.measured) return null;
  const { measured } = warning;
  const distance = distanceInDisplayUnit(measured.km - warning.origin_km, units);
  const minutes = Math.round((measured.surge_t - warning.surge_t) / 60);
  const speed = speedInDisplayUnit(measured.speed_kmh, units);
  return `Measured: ${distance} in ${minutes} min = ${speed} (${nameOf(warning.origin)} to ${nameOf(measured.node)})`;
}

export function riverKm(km: number): string {
  return `River km ${km.toFixed(1).replace("-", "−")}`;
}

// "5.1 ft and rising 1.4 ft an hour"; metres until the Region is known.
export function stormSurgeLevel(warning: StormSurgeWarning, units: DisplayUnits | null): string {
  const length = (metres: number) =>
    units ? inDisplayUnit(metres * 100, "water_level", units) : `${metres.toFixed(2)} m`;
  const rise =
    warning.rise_m_per_h === null ? "rising" : `rising ${length(warning.rise_m_per_h)} an hour`;
  return warning.level_m === null ? rise : `${length(warning.level_m)} and ${rise}`;
}

// "Water is surging at S0, 12.2 km upstream of this Node". The distance needs both River kms and
// an origin above this Node; otherwise the sentence says where the Sensor sits on the river.
export function warningSentence(
  warning: CommunityWarning,
  nodes: NodeSnapshot[],
  thisNodeId: string,
  units: DisplayUnits | null,
): string {
  const origin = nodes.find((node) => node.id === warning.origin);
  const originName = origin?.name ?? warning.origin;
  if (warning.hazard === "storm_surge") {
    return `Water at ${originName} is ${stormSurgeLevel(warning, units)}`;
  }
  const here = nodes.find((node) => node.id === thisNodeId);
  const what = `${reasonsSentence(warning)} at ${originName}`;
  const upstreamKm = here?.river_km != null ? here.river_km - warning.origin_km : null;
  return upstreamKm !== null && upstreamKm > 0
    ? `${what}, ${distanceInDisplayUnit(upstreamKm, units)} upstream of this Node`
    : `${what}, ${riverKm(warning.origin_km)}`;
}
