import type { FlashFloodWarning } from "./communityWarnings";
import type { Home } from "./householdProfile";

// One stretch of river with a single reconstructed wave speed; `km[i]` is the River km at `points[i]`.
type RiverReach = { speedKmh: number; points: [number, number][]; km: number[] };
export type RiverLine = RiverReach[];

// A home farther from the river line than this is not on the river, so no wave is "coming to" it.
export const MAX_DISTANCE_TO_RIVER_KM = 2;

const EARTH_RADIUS_KM = 6371;
const SECONDS_PER_HOUR = 3600;

type GeoJsonReach = {
  properties?: { speed_kmh?: unknown; km?: unknown };
  geometry?: { coordinates?: unknown };
};

// The pack's river.geojson: one LineString per reach, GeoJSON order (lon, lat).
export function parseRiverLine(geojson: unknown): RiverLine {
  const features = (geojson as { features?: GeoJsonReach[] } | null)?.features;
  if (!Array.isArray(features)) throw new Error("river.geojson is not a river line");
  return features.map(({ properties, geometry }) => {
    const { speed_kmh: speedKmh, km } = properties ?? {};
    const coordinates = geometry?.coordinates;
    if (
      typeof speedKmh !== "number" ||
      !Array.isArray(km) ||
      !Array.isArray(coordinates) ||
      km.length !== coordinates.length
    ) {
      throw new Error("river.geojson has a reach without speed_kmh, km and coordinates");
    }
    return {
      speedKmh,
      km: km as number[],
      points: (coordinates as [number, number][]).map(([lon, lat]) => [lat, lon]),
    };
  });
}

export function distanceKm(a: Home, [lat, lon]: [number, number]): number {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const deltaLat = toRadians(lat - a.lat);
  const deltaLon = toRadians(lon - a.lon);
  const h =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(a.lat)) * Math.cos(toRadians(lat)) * Math.sin(deltaLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

// The River km of the vertex nearest home, or null when home is not near the river.
export function riverKmOfHome(river: RiverLine, home: Home): number | null {
  let nearestKm: number | null = null;
  let nearestDistance = Infinity;
  for (const { points, km } of river) {
    for (let i = 0; i < points.length; i++) {
      const distance = distanceKm(home, points[i]);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestKm = km[i];
      }
    }
  }
  return nearestDistance <= MAX_DISTANCE_TO_RIVER_KM ? nearestKm : null;
}

function travelSeconds(river: RiverLine, fromKm: number, toKm: number): number {
  let seconds = 0;
  for (const { speedKmh, km } of river) {
    const overlapKm = Math.min(toKm, km[km.length - 1]) - Math.max(fromKm, km[0]);
    if (overlapKm > 0) seconds += (overlapKm / speedKmh) * SECONDS_PER_HOUR;
  }
  return seconds;
}

// Below the second Node the measured speed replaces the reconstructed reaches, counted from that
// Node's own Surge; above it the reconstructed speeds from the origin still apply.
function arrivalAt(river: RiverLine, warning: FlashFloodWarning, homeKm: number): number {
  const { measured } = warning;
  if (measured && homeKm > measured.km) {
    return measured.surge_t + ((homeKm - measured.km) / measured.speed_kmh) * SECONDS_PER_HOUR;
  }
  return warning.surge_t + travelSeconds(river, warning.origin_km, homeKm);
}

export type WaveArrival =
  // Event time (Unix seconds) at which the wave reaches home.
  { kind: "expected"; at: number } | { kind: "not-near-river" };

// The earliest Event time at which any warning's wave reaches this River km; null when every
// origin is at or below it. The map's front and town stamps read it too, so they agree with the ETA.
export function arrivalAtKm(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  riverKm: number,
): number | null {
  const arrivals = warnings
    .filter((warning) => warning.origin_km < riverKm)
    .map((warning) => arrivalAt(river, warning, riverKm));
  return arrivals.length === 0 ? null : Math.min(...arrivals);
}

// The earliest arrival over all warnings whose origin is upstream of home; null when no warning
// has an ETA for this home (none yet, or every origin is at or below it).
export function waveArrival(
  river: RiverLine,
  home: Home,
  warnings: FlashFloodWarning[],
): WaveArrival | null {
  if (warnings.length === 0) return null;
  const homeKm = riverKmOfHome(river, home);
  if (homeKm === null) return { kind: "not-near-river" };
  const at = arrivalAtKm(river, warnings, homeKm);
  return at === null ? null : { kind: "expected", at };
}

export function waveEtaLine(arrivalAt: number, eventT: number): string {
  const secondsLeft = arrivalAt - eventT;
  if (secondsLeft <= 0) return "Wave expected now";
  return `Wave expected at your home in about ${Math.ceil(secondsLeft / 60)} min`;
}

// Where the wave front is on the river at `eventT`, as a River km: the furthest any warning's front
// has got, or null while no warning has started a wave. Found by inverting the arrival time, which
// grows with River km.
export function waveFrontKm(
  river: RiverLine,
  warnings: FlashFloodWarning[],
  eventT: number,
): number | null {
  const endKm = Math.max(...river.map(({ km }) => km[km.length - 1]));
  const fronts = warnings
    .filter((warning) => warning.surge_t < eventT)
    .map((warning) => {
      let behind = warning.origin_km;
      let ahead = endKm;
      for (let step = 0; step < 40; step++) {
        const middle = (behind + ahead) / 2;
        if (arrivalAt(river, warning, middle) <= eventT) behind = middle;
        else ahead = middle;
      }
      return behind;
    });
  return fronts.length === 0 ? null : Math.max(...fronts);
}
