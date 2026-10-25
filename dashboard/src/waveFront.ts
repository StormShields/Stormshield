import type { FlashFloodWarning } from "./communityWarnings";
import type { NodeOnMap } from "./nodesOnMap";
import type { Place } from "./placeLabels";
import type { LatLon } from "./routeGrid";
import { arrivalAtKm, riverKmOfHome, waveFrontKm, type RiverLine } from "./waveEta";

// How far behind the head the trail reaches (D-17), and how long a Node stays wave-white (D-18).
export const WAVE_TRAIL_KM = 15;
export const WAVE_FLASH_SECONDS = 120;

// The spot on the river at this River km; null outside the river line.
export function pointAtKm(river: RiverLine, riverKm: number): LatLon | null {
  for (const { km, points } of river) {
    if (riverKm < km[0] || riverKm > km[km.length - 1]) continue;
    for (let i = 1; i < km.length; i++) {
      if (riverKm > km[i]) continue;
      const along = km[i] === km[i - 1] ? 0 : (riverKm - km[i - 1]) / (km[i] - km[i - 1]);
      return [
        points[i - 1][0] + (points[i][0] - points[i - 1][0]) * along,
        points[i - 1][1] + (points[i][1] - points[i - 1][1]) * along,
      ];
    }
  }
  return null;
}

// The river line between two River km, vertex by vertex, ending exactly on both.
function stretchBetween(river: RiverLine, fromKm: number, toKm: number): LatLon[] {
  const line: LatLon[] = [];
  const start = pointAtKm(river, fromKm);
  if (start) line.push(start);
  for (const { km, points } of river) {
    km.forEach((vertexKm, i) => {
      if (vertexKm > fromKm && vertexKm < toKm) line.push(points[i]);
    });
  }
  const end = pointAtKm(river, toKm);
  if (end) line.push(end);
  return line;
}

export type WaveFront = {
  head: LatLon;
  // From the tail to the head; the head end is the bright one.
  trail: LatLon[];
};

// The comet on the river at `eventT`; null while no warning has started a wave.
export function waveFront(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  eventT: number,
): WaveFront | null {
  const headKm = waveFrontKm(river, warnings, eventT);
  if (headKm === null) return null;
  const head = pointAtKm(river, headKm);
  if (!head) return null;
  const startKm = Math.min(...warnings.map((warning) => warning.origin_km));
  return { head, trail: stretchBetween(river, Math.max(startKm, headKm - WAVE_TRAIL_KM), headKm) };
}

// The Nodes the front passed within the last two event minutes: they show wave-white, then go
// back to their real state. A Node at or above the origin is never passed.
export function nodesTheWavePassed(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  nodes: Pick<NodeOnMap, "id" | "riverKm">[],
  eventT: number,
): string[] {
  return nodes
    .filter((node) => {
      if (node.riverKm === null) return false;
      const passedAt = arrivalAtKm(river, warnings, node.riverKm);
      return passedAt !== null && passedAt <= eventT && eventT < passedAt + WAVE_FLASH_SECONDS;
    })
    .map((node) => node.id);
}

// The places the front has reached, with the Event time it did; a stamp stays for the rest of the
// replay (D-21). Only places on the river line (within the ETA's own distance) are ever reached.
export function townsTheWaveReached(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  places: Place[],
  eventT: number,
): Map<string, number> {
  const reached = new Map<string, number>();
  for (const place of places) {
    const riverKm = riverKmOfHome(river, place);
    if (riverKm === null) continue;
    const at = arrivalAtKm(river, warnings, riverKm);
    if (at !== null && at <= eventT) reached.set(place.name, at);
  }
  return reached;
}
