import { inFloodProneArea, type FloodProneAreas } from "./floodProne";
import { cardReasons, reasonSentence } from "./floodRiskSentences";
import type { Home, HouseholdProfile } from "./householdProfile";
import { appliesToHousehold, type OfficialAlert } from "./officialAlerts";
import type { LatLon, RouteGrid, Routes } from "./routeGrid";
import type { FloodRisk, Hazard, Region } from "./nodeState";
import { rerouteHome, routeIsAffected, type BlockedRoad, type RoadGraph } from "./rerouting";

export type Shelter = {
  id: string;
  name: string;
  pos: [number, number];
  special_needs: boolean;
  pet_friendly: boolean;
  // Only a river Region's Shelters have one.
  height_above_river_m?: number;
};

// A hand-placed spot above a town (`scripts/pack_high_ground.py`); not a Shelter, never open or closed.
export type HighGroundPoint = {
  id: string;
  name: string;
  pos: [number, number];
  town: string;
  climb_m: number;
  // From the town's key place; the resident's own walk is worked out from home.
  walk_minutes: number;
};

// A High-ground point worth showing to this household, with the walk from their home.
export type HighGroundPin = { point: HighGroundPoint; walkMinutes: number; nearest: boolean };

// What the map draws from a pack that holds the Region's basemap and terrain.
export type Basemap = {
  // [south, west, north, east], the Region's box: the map frames it.
  bbox: [number, number, number, number];
  terrain: {
    approximate: boolean;
    // [lowest, highest] zoom of the elevation tiles.
    zooms: [number, number];
  };
  credits: { layer: string; credit: string; checked: string }[];
};

export type CachePackContents = {
  shelters: Shelter[];
  // Empty for a pack built before High-ground points.
  highGround: HighGroundPoint[];
  floodProne: FloodProneAreas;
  routeGrid: RouteGrid | null;
  // [south, west, north, east], the area the pack covers; null when its manifest has none.
  bbox: [number, number, number, number] | null;
  // ISO time the pack was built; null when its manifest has none.
  built: string | null;
  // Null for a pack built without a basemap (the map then draws only the Region's own layers).
  basemap: Basemap | null;
};

// What the phone needs to find its own way when the precomputed Route will not do.
type Rerouting = { graph: RoadGraph; blocked: BlockedRoad[] };

export type EvacuationPlan = {
  risk: { level: NonNullable<FloodRisk["level"]>; reasons: string[] } | null;
  // Official Alerts that apply to this household, oldest first; the plan only ever quotes them.
  officialAlerts: OfficialAlert[];
  lines: string[];
  shelter: Shelter | null;
  // With a wave coming and no Shelter reachable in time, the closest one outside the Flood-Prone
  // Area, so the map still shows which way is uphill; never a place the plan calls safe.
  outOfReachShelter: Shelter | null;
  // Shown on the map only while the plan says to get to higher ground; nearest first.
  highGround: HighGroundPin[];
  // From the Grid point nearest home to the Shelter; null when the plan has no Route to draw.
  route: LatLon[] | null;
  officialLine: string;
};

export const OFFICIAL_LINE = "Evacuation decisions come from official sources.";
// A coast has no river: the water, not a wave, is what is coming.
const higherGroundLine = (coast: boolean) =>
  `No Shelter you can reach in time. Get to higher ground, away from the ${coast ? "water" : "river"}, now.`;

// When the wave reaches home, on the Event clock (Unix seconds), and what the clock says now.
export type WaveWindow = { arrivalAt: number; eventT: number };

// A Shelter must be reached this long before the wave, to leave room for a slower walk.
const SAFETY_MARGIN_SECONDS = 5 * 60;
// Roads and paths wind, so the walk is longer than the straight line.
const DETOUR_FACTOR = 1.4;
const WALKING_SPEED_KMH = 4;

// A High-ground point further from home than this is not offered: the walk is too far to count on.
const HIGH_GROUND_RANGE_KM = 2;

const EARTH_RADIUS_KM = 6371;

function distanceKm(from: Home, [lat, lon]: LatLon): number {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const deltaLat = toRadians(lat - from.lat);
  const deltaLon = toRadians(lon - from.lon);
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(from.lat)) * Math.cos(toRadians(lat)) * Math.sin(deltaLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

function routeLengthKm(route: LatLon[]): number {
  let total = 0;
  for (let i = 1; i < route.length; i++) {
    total += distanceKm({ lat: route[i - 1][0], lon: route[i - 1][1] }, route[i]);
  }
  return total;
}

const secondsUntil = ({ arrivalAt, eventT }: WaveWindow) => arrivalAt - eventT;

function walkingSeconds(from: Home, to: LatLon): number {
  return ((distanceKm(from, to) * DETOUR_FACTOR) / WALKING_SPEED_KMH) * 3600;
}

const minutesRoundedUp = (seconds: number) => Math.ceil(seconds / 60);

function waveWords(secondsLeft: number, coast: boolean): string {
  const noun = coast ? "water" : "wave";
  return secondsLeft > 0
    ? `${noun} in ${minutesRoundedUp(secondsLeft)} min`
    : `${noun} expected now`;
}

function walkAndWave(home: Home, shelter: Shelter, secondsLeft: number, coast: boolean): string {
  const walk = minutesRoundedUp(walkingSeconds(home, shelter.pos));
  return `${walk} min walk, ${waveWords(secondsLeft, coast)}.`;
}

export function highGroundLabel(climbM: number, walkMinutes: number): string {
  return `${climbM} m up · ${walkMinutes} min walk`;
}

function highGroundNear(home: Home, points: HighGroundPoint[]): HighGroundPin[] {
  return points
    .filter((point) => distanceKm(home, point.pos) <= HIGH_GROUND_RANGE_KM)
    .sort((a, b) => distanceKm(home, a.pos) - distanceKm(home, b.pos))
    .map((point, index) => ({
      point,
      walkMinutes: minutesRoundedUp(walkingSeconds(home, point.pos)),
      nearest: index === 0,
    }));
}

type Candidate = { shelter: Shelter; route: LatLon[] | null; km: number };

function describe({ shelter, route, km }: Candidate, showHeight: boolean): string {
  const features = [
    shelter.special_needs && "special-needs",
    shelter.pet_friendly && "pet-friendly",
  ]
    .filter(Boolean)
    .join(", ");
  const distance = route
    ? `${km.toFixed(1)} km by road`
    : `${km.toFixed(1)} km away in a straight line, no road route available`;
  const height =
    showHeight && shelter.height_above_river_m !== undefined
      ? `, ${shelter.height_above_river_m} m above the river`
      : "";
  return `Nearest open Shelter: ${shelter.name}, ${distance}${height}${features ? ` (${features})` : ""}.`;
}

// A Shelter with no Route from home's Grid point ranks after every one that has a Route.
function byRoadThenStraightLine(a: Candidate, b: Candidate): number {
  if ((a.route === null) !== (b.route === null)) return a.route === null ? 1 : -1;
  return a.km - b.km;
}

type NearestShelter = {
  shelter: Shelter | null;
  outOfReachShelter?: Shelter;
  highGround?: HighGroundPin[];
  route: LatLon[] | null;
  lines: string[];
};

function nearestFittingShelter(
  profile: HouseholdProfile,
  pack: CachePackContents,
  openShelterIds: string[],
  routes: Routes | null,
  rerouting: Rerouting | null,
  wave: WaveWindow | null,
  coast: boolean,
): NearestShelter {
  const open = pack.shelters.filter((shelter) => openShelterIds.includes(shelter.id));
  if (open.length === 0) {
    return {
      shelter: null,
      route: null,
      lines: ["No open Shelter announced yet. Follow official sources."],
    };
  }
  // A need is a filter: a household without it can still use a Shelter that offers it.
  const fitting = open.filter(
    (shelter) =>
      (!profile.needsSpecialNeedsShelter || shelter.special_needs) &&
      (!profile.needsPetFriendlyShelter || shelter.pet_friendly),
  );
  if (fitting.length === 0) {
    return {
      shelter: null,
      route: null,
      lines: ["No open Shelter matches this household. Follow official sources."],
    };
  }
  const outsideFloodProneArea = (shelter: Shelter) =>
    !inFloodProneArea({ lat: shelter.pos[0], lon: shelter.pos[1] }, pack.floodProne);
  // On a coast the land below the flood line is where the water goes: no Shelter there is offered,
  // wave or not.
  const usable = coast ? fitting.filter(outsideFloodProneArea) : fitting;
  if (usable.length === 0) {
    return {
      shelter: null,
      route: null,
      lines: ["No open Shelter outside the Flood-Prone Area. Follow official sources."],
    };
  }
  const secondsLeft = wave ? secondsUntil(wave) : 0;
  const reachable = wave
    ? usable.filter(
        (shelter) =>
          outsideFloodProneArea(shelter) &&
          walkingSeconds(profile.home, shelter.pos) < secondsLeft - SAFETY_MARGIN_SECONDS,
      )
    : usable;
  if (wave && reachable.length === 0) {
    const byDistance = [...usable].sort(
      (a, b) => distanceKm(profile.home, a.pos) - distanceKm(profile.home, b.pos),
    );
    const outOfReachShelter = byDistance.find(outsideFloodProneArea);
    const closest = outOfReachShelter ?? byDistance[0];
    const highGround = highGroundNear(profile.home, pack.highGround);
    const [nearestHighGround] = highGround;
    return {
      shelter: null,
      outOfReachShelter,
      highGround,
      route: null,
      lines: [
        `Nearest Shelter ${closest.name}: ${walkAndWave(profile.home, closest, secondsLeft, coast)}`,
        higherGroundLine(coast),
        ...(nearestHighGround
          ? [
              `Nearest high ground: ${nearestHighGround.point.name}, ${highGroundLabel(
                nearestHighGround.point.climb_m,
                nearestHighGround.walkMinutes,
              )}.`,
            ]
          : []),
      ],
    };
  }
  const candidates = reachable
    .map((shelter): Candidate => {
      const route = routes?.[shelter.id] ?? null;
      return {
        shelter,
        route,
        km: route ? routeLengthKm(route) : distanceKm(profile.home, shelter.pos),
      };
    })
    .sort(byRoadThenStraightLine);
  const [nearest] = candidates;
  const rerouted =
    rerouting && reroutedPlan(profile, pack, reachable, nearest, rerouting, wave, coast);
  if (rerouted) return rerouted;
  const lines = [describe(nearest, wave !== null)];
  if (wave) lines.push(walkAndWave(profile.home, nearest.shelter, secondsLeft, coast));
  if (nearest.route) {
    lines.push("The route is the shortest by road and ignores flooding and road closures.");
  }
  return { shelter: nearest.shelter, route: nearest.route, lines };
}

// A Route is replaced only when it is affected: it runs along a Blocked Road or through a
// Flood-Prone Area, or a resident has blocked roads and there is no Route to draw at all.
function reroutedPlan(
  profile: HouseholdProfile,
  pack: CachePackContents,
  reachable: Shelter[],
  nearest: Candidate,
  { graph, blocked }: Rerouting,
  wave: WaveWindow | null,
  coast: boolean,
): { shelter: Shelter | null; route: LatLon[] | null; lines: string[] } | null {
  const affected = nearest.route
    ? routeIsAffected(nearest.route, graph, blocked, pack.floodProne)
    : blocked.length > 0;
  if (!affected) return null;
  const reached = rerouteHome({
    graph,
    home: profile.home,
    shelters: reachable,
    blocked,
    floodProne: pack.floodProne,
  });
  // Without Blocked Roads, "nothing reachable" is the graph's doing, so the warning would be wrong.
  if (reached === null || (reached.length === 0 && blocked.length === 0)) return null;
  if (reached.length === 0) {
    return {
      shelter: nearest.shelter,
      route: null,
      lines: [
        describe(
          { ...nearest, route: null, km: distanceKm(profile.home, nearest.shelter.pos) },
          wave !== null,
        ),
        "Roads you marked as blocked cut off every Shelter. Follow official sources.",
      ],
    };
  }
  const [best] = reached;
  const lines = [describe(best, wave !== null)];
  if (wave) lines.push(walkAndWave(profile.home, best.shelter, secondsUntil(wave), coast));
  if (blocked.length > 0) {
    lines.push(`Rerouted around ${blocked.length} blocked road${blocked.length === 1 ? "" : "s"}.`);
  }
  lines.push(
    best.crossesFloodProneArea
      ? "This route still crosses a Flood-Prone Area."
      : "The route avoids the mapped Flood-Prone Areas.",
  );
  return { shelter: best.shelter, route: best.route, lines };
}

export function evacuationPlan({
  profile,
  pack,
  openShelterIds,
  floodRisk,
  routes,
  rerouting,
  officialAlerts,
  wave,
  region,
  hazard,
}: {
  profile: HouseholdProfile | null;
  pack: CachePackContents | null;
  openShelterIds: string[];
  floodRisk: FloodRisk | null;
  region: Region | null;
  hazard: Hazard | null;
  routes: Routes | null;
  rerouting: Rerouting | null;
  officialAlerts: OfficialAlert[];
  // Null with no Community Warning, or none with a Wave ETA for this home.
  wave: WaveWindow | null;
}): EvacuationPlan {
  const risk =
    floodRisk?.level && region && hazard
      ? {
          level: floodRisk.level,
          reasons: cardReasons(floodRisk).map((reason) => reasonSentence(reason, region, hazard)),
        }
      : null;
  const plan = {
    risk,
    officialAlerts: [] as OfficialAlert[],
    lines: [] as string[],
    shelter: null,
    outOfReachShelter: null,
    highGround: [] as HighGroundPin[],
    route: null,
    officialLine: OFFICIAL_LINE,
  };

  if (profile === null) {
    return {
      ...plan,
      lines: ["Fill in your household profile to see your Flood-Prone Area and nearest Shelter."],
    };
  }
  if (pack === null) {
    return {
      ...plan,
      // Without the pack the home might be in the Flood-Prone Area, and a missed alert is worse.
      officialAlerts: officialAlerts.filter((alert) => appliesToHousehold(alert, profile, true)),
      lines: [
        "Shelter and flood-area information is still loading on this Node. Follow official sources.",
      ],
    };
  }

  const homeInFloodProneArea = inFloodProneArea(profile.home, pack.floodProne);
  const area = homeInFloodProneArea
    ? "Your home is inside a mapped Flood-Prone Area."
    : "Your home is outside the mapped Flood-Prone Areas (approximate).";
  const { shelter, outOfReachShelter, highGround, route, lines } = nearestFittingShelter(
    profile,
    pack,
    openShelterIds,
    routes,
    rerouting,
    wave,
    region?.water_type === "coast",
  );
  return {
    ...plan,
    officialAlerts: officialAlerts.filter((alert) =>
      appliesToHousehold(alert, profile, homeInFloodProneArea),
    ),
    lines: [area, ...lines],
    shelter,
    outOfReachShelter: outOfReachShelter ?? null,
    highGround: highGround ?? [],
    route,
  };
}
