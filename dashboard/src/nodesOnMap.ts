import { measurementInDisplayUnit } from "./displayUnits";
import type { DisplayUnits, Measurement, NodeLevel, NodeState, ReadingKind } from "./nodeState";

export type NodeOnMap = {
  id: string;
  // This Node's own entry; it stays above the "Not counted" divider even when Unverified.
  isThisNode: boolean;
  label: string;
  position: [number, number];
  // Where the Node sits along the river; null off the river.
  riverKm: number | null;
  // In centimetres, the unit the Rule set and the rising water are worked out in.
  waterLevelCm: number | null;
  // The same level as residents read it, in the Region's unit: "3.2 ft".
  waterLevelShown: string | null;
  simulated: boolean;
  stale: boolean;
  // False for an Unverified Node: shown, but not counted toward Flood Risk.
  registered: boolean;
  level: NodeLevel | null;
  ageSeconds: number;
  // `value` and `unit` are the Node's own (cm, mm/h, hPa, …); `shown` is the Region's.
  measurements: ({ kind: ReadingKind; shown: string } & Measurement)[];
};

// The Node sends water level in metres; the dashboard shows it in centimetres. A pack built
// before the wire format changed still says centimetres, and is shown as it is.
function displayed(kind: ReadingKind, measurement: Measurement): Measurement {
  if (kind === "water_level" && measurement.unit === "m") {
    return { value: Math.round(measurement.value * 1000) / 10, unit: "cm" };
  }
  return measurement;
}

function displayedMeasurements(
  measurements: Partial<Record<ReadingKind, Measurement>>,
  units: DisplayUnits,
): NodeOnMap["measurements"] {
  return (Object.entries(measurements) as [ReadingKind, Measurement][]).map(
    ([kind, measurement]) => {
      const own = displayed(kind, measurement);
      return { kind, ...own, shown: measurementInDisplayUnit(kind, own, units) };
    },
  );
}

function waterLevelCm(measurements: Partial<Record<ReadingKind, Measurement>>): number | null {
  const water = measurements.water_level;
  return water ? displayed("water_level", water).value : null;
}

function waterLevelShown(
  measurements: Partial<Record<ReadingKind, Measurement>>,
  units: DisplayUnits,
): string | null {
  const water = measurements.water_level;
  return water
    ? measurementInDisplayUnit("water_level", displayed("water_level", water), units)
    : null;
}

// A Node knows its own name; everyone else is shown by the name in the registry, or by id when
// the Hub has no name for them. Ordered for the cards: this Node, the other Registered Nodes by
// label, then the Unverified ones by id.
export function nodesOnMap(state: NodeState | null): NodeOnMap[] {
  if (!state) return [];
  const units = state.region.display_units;
  const nodes = state.nodes.map((node) => ({
    id: node.id,
    isThisNode: node.id === state.id,
    label: node.id === state.id ? state.name : (node.name ?? node.id),
    position: node.position,
    riverKm: node.river_km,
    waterLevelCm: waterLevelCm(node.measurements),
    waterLevelShown: waterLevelShown(node.measurements, units),
    simulated: node.simulated,
    stale: node.stale,
    registered: node.registered,
    level: state.flood_risk.nodes[node.id] ?? null,
    ageSeconds: node.age_s,
    measurements: displayedMeasurements(node.measurements, units),
  }));
  const rank = (node: NodeOnMap) => (node.isThisNode ? 0 : node.registered ? 1 : 2);
  return nodes.sort((a, b) => rank(a) - rank(b) || a.label.localeCompare(b.label));
}
