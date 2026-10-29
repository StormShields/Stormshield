import type { NodeSnapshot, NodeState, Region } from "./nodeState";

// Nepal's Region as a Node reports it.
export const FAKE_REGION: Region = {
  name: "nepal",
  label: "Bhote Koshi valley, Nepal",
  water_type: "river",
  storm_surge: null,
  time_zone: "Asia/Kathmandu",
  display_units: {
    water_level: "cm",
    rain_rate: "mm/h",
    soil_moisture: "%",
    air_pressure: "hPa",
    distance: "km",
  },
  official_alert_sources: [
    { tag: "dhm", name: "DHM", covers: "Nepal" },
    { tag: "ndrrma", name: "NDRRMA", covers: "Nepal" },
    { tag: "district", name: "District authorities", covers: "Rasuwa district" },
  ],
};

// Fort Myers' Region as a Node reports it: Eastern time, feet and miles.
export const FORT_MYERS_REGION: Region = {
  name: "fort-myers",
  label: "Fort Myers Beach and Estero Bay, Florida",
  water_type: "coast",
  storm_surge: { rising_window_s: 900, flood_prone_below_cm: 274.32 },
  time_zone: "America/New_York",
  display_units: {
    water_level: "ft",
    rain_rate: "in/h",
    soil_moisture: "%",
    air_pressure: "inHg",
    distance: "mi",
  },
  official_alert_sources: [{ tag: "nws", name: "National Weather Service", covers: "Lee County" }],
};

// What a Node answers at /api/state on a calm day with no Node heard yet; tests override the rest.
export function fakeNodeState(overrides: Partial<NodeState> = {}): NodeState {
  return {
    id: "porch",
    name: "porch",
    role: "hub",
    status: "online",
    registration: "registered",
    sandbox: null,
    region: FAKE_REGION,
    hazard: "flash_flood",
    live: false,
    flood_risk: {
      level: null,
      reasons: [],
      storm_signal: { on: false, nodes: 0, pressure_hpa: null },
      nodes: {},
      surged: [],
    },
    nodes: [],
    official_alerts: [],
    community_warnings: [],
    official_gauges: [],
    ...overrides,
  };
}

export function fakeNodeSnapshot(id: string, overrides: Partial<NodeSnapshot> = {}): NodeSnapshot {
  return {
    id,
    position: [29.652, -82.324],
    river_km: null,
    simulated: true,
    age_s: 2,
    stale: false,
    counts: true,
    measurements: { air_pressure: { value: 1015, unit: "hPa" } },
    registered: true,
    name: id,
    ...overrides,
  };
}
