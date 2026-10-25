import type { FlashFloodWarning } from "./communityWarnings";
import type { NodeOnMap } from "./nodesOnMap";
import type { LatLon } from "./routeGrid";
import { pointAtKm } from "./waveFront";
import { arrivalAtKm, type RiverLine } from "./waveEta";

// The height line is a drawn gauge, not a flood map (D-46): each metre of water is drawn this far
// to the side of the river, so a rising level reads as a widening. The metres are the reading's.
const DRAWN_M_PER_WATER_M = 300;
// A reach is the stretch of river a Node's reading stands for, this far up and down from it.
const REACH_HALF_KM = 1.5;
const TICK_HALF_KM = 0.4;
const SAMPLE_EVERY_KM = 0.5;
const M_PER_DEGREE = 111_320;

export type WaterReach = {
  riverKm: number;
  levelM: number;
  at: LatLon;
  // The two dashed lines, one either side of the river.
  lines: LatLon[][];
  // One short rung per whole metre, on each side.
  ticks: LatLon[][];
};

// The point `metres` to the left (positive) or right (negative) of the river at this River km.
function beside(river: RiverLine, riverKm: number, metres: number): LatLon | null {
  const here = pointAtKm(river, riverKm);
  if (!here) return null;
  const [fromLat, fromLon] = pointAtKm(river, riverKm - 0.1) ?? here;
  const [toLat, toLon] = pointAtKm(river, riverKm + 0.1) ?? here;
  const cosLat = Math.cos((here[0] * Math.PI) / 180);
  const east = (toLon - fromLon) * cosLat;
  const north = toLat - fromLat;
  const length = Math.hypot(east, north);
  if (length === 0) return here;
  const offsetNorth = (east / length) * metres;
  const offsetEast = (-north / length) * metres;
  return [here[0] + offsetNorth / M_PER_DEGREE, here[1] + offsetEast / (M_PER_DEGREE * cosLat)];
}

function reachOf(river: RiverLine, riverKm: number, levelM: number): WaterReach | null {
  const at = pointAtKm(river, riverKm);
  if (!at) return null;
  const sides = [1, -1];
  const lines = sides.map((side) => {
    const line: LatLon[] = [];
    for (
      let km = riverKm - REACH_HALF_KM;
      km <= riverKm + REACH_HALF_KM + 1e-9;
      km += SAMPLE_EVERY_KM
    ) {
      const point = beside(river, km, side * levelM * DRAWN_M_PER_WATER_M);
      if (point) line.push(point);
    }
    return line;
  });
  const ticks: LatLon[][] = [];
  for (const side of sides) {
    for (let metre = 1; metre <= Math.floor(levelM); metre++) {
      const rung = [riverKm - TICK_HALF_KM, riverKm + TICK_HALF_KM]
        .map((km) => beside(river, km, side * metre * DRAWN_M_PER_WATER_M))
        .filter((point): point is LatLon => point !== null);
      if (rung.length === 2) ticks.push(rung);
    }
  }
  return { riverKm, levelM, at, lines: lines.filter((line) => line.length >= 2), ticks };
}

// The water levels to draw at `eventT`: one reach per Node on the river the wave has reached,
// at that Node's last reported level. A Node that went silent keeps its last level, which is
// the peak it saw. Nothing is drawn before a warning has started a wave.
export function waterReaches(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  nodes: Pick<NodeOnMap, "riverKm" | "waterLevelCm">[],
  eventT: number,
): WaterReach[] {
  if (warnings.length === 0) return [];
  const reaches: WaterReach[] = [];
  for (const node of nodes) {
    if (node.riverKm === null || node.waterLevelCm === null) continue;
    const km = node.riverKm;
    const atOrigin = warnings.some((warning) => Math.abs(warning.origin_km - km) < 0.05);
    const arrival = arrivalAtKm(river, warnings, km);
    if (!atOrigin && (arrival === null || arrival > eventT)) continue;
    const reach = reachOf(river, km, node.waterLevelCm / 100);
    if (reach) reaches.push(reach);
  }
  return reaches;
}
