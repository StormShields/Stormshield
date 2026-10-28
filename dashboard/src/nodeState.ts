import type { CommunityWarning } from "./communityWarnings";
import type { OfficialAlert } from "./officialAlerts";

export type NodeLevel = "elevated" | "high";

// What a Region's water can do; it names the Event and decides what triggers a Community Warning.
export type Hazard = "flash_flood" | "storm_surge";

export type DisplayUnits = {
  water_level: "cm" | "m" | "ft";
  rain_rate: "mm/h" | "in/h";
  soil_moisture: "%";
  air_pressure: "hPa" | "inHg";
  distance: "km" | "mi";
};

// The part of the Region file the browser needs; the Node has already checked the rest.
export type Region = {
  name: string;
  label: string;
  // A river Region draws a hand-made corridor; a coast Region traces its Flood-Prone Area.
  water_type: "river" | "coast";
  // The coast thresholds a Viewer needs for its own Water ETA, in cm; null on a river.
  storm_surge: { rising_window_s: number; flood_prone_below_cm: number } | null;
  time_zone: string;
  display_units: DisplayUnits;
  // An Official Alert names its source by `tag`; the Region says what to call it.
  official_alert_sources: { tag: string; name: string; covers: string }[];
};

export type FloodRiskReason = {
  code:
    "water_surge" | "water_high" | "water_rising" | "rain_heavy" | "pressure_falling" | "raining";
  nodes: number;
  value: number;
  seconds?: number | null;
};

export type FloodRisk = {
  level: "low" | "elevated" | "high" | null;
  reasons: FloodRiskReason[];
  storm_signal: { on: boolean; nodes: number; pressure_hpa: number | null };
  nodes: Record<string, NodeLevel | null>;
  surged: string[];
};

// The flood-warning kinds are water_level (m), rain_rate (mm/h), soil_moisture (%) and air_pressure
// (hPa); a Node may send any other kind, and it is shown with the unit it came with.
export type ReadingKind = string;

export type Measurement = { value: number; unit: string };

// What this Node last heard from one Node. The Node decides `stale`, so the browser never does.
export type NodeSnapshot = {
  id: string;
  position: [number, number];
  // Where the operator put it along the river; null when it was not told.
  river_km: number | null;
  simulated: boolean;
  age_s: number;
  stale: boolean;
  // False once the Node has been silent for 60 s: Flood Risk and Community Warnings ignore it.
  counts: boolean;
  measurements: Partial<Record<ReadingKind, Measurement>>;
  // Only Registered Nodes count toward Flood Risk; `name` is the Hub's name for it, null if none.
  registered: boolean;
  name: string | null;
};

type NodeStatus = "online" | "mesh_only";

// Where this Node stands with the Hub; the Hub itself is always registered.
export type Registration = "unverified" | "waiting" | "registered";

// A government water-level station of the Region, with the newest level this Node has heard from
// the Hub; `level_m` is metres in the Region's datum and null until the Hub has sent one.
export type OfficialGauge = {
  agency: string;
  station: string;
  label: string;
  pos: [number, number];
  level_m: number | null;
  // Unix seconds, when the agency measured it.
  observed: number | null;
};

// The answer of GET /api/state: one consistent instant of this Node's view of the Mesh.
export type NodeState = {
  id: string;
  name: string;
  role: "sensor" | "hub";
  status: NodeStatus;
  registration: Registration;
  // Present only when the Node is the Sandbox's Hub; nothing in the Sandbox is a real reading.
  sandbox: { label: "SIMULATED" } | null;
  region: Region;
  hazard: Hazard;
  flood_risk: FloodRisk;
  nodes: NodeSnapshot[];
  official_alerts: OfficialAlert[];
  // Only warnings whose Hub signature this Node verified.
  community_warnings: CommunityWarning[];
  official_gauges: OfficialGauge[];
};
