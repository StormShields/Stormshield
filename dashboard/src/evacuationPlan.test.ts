import {
  evacuationPlan,
  OFFICIAL_LINE,
  highGroundLabel,
  type CachePackContents,
  type HighGroundPoint,
  type Shelter,
} from "./evacuationPlan";
import type { HouseholdProfile } from "./householdProfile";
import type { OfficialAlert } from "./officialAlerts";
import type { Routes } from "./routeGrid";
import { NEPAL_REGION, FAKE_REGION } from "./fakeNodeState";
import type { FloodRisk } from "./nodeState";

const HOME = { lat: 29.65, lon: -82.32 };

const NEAR_PLAIN: Shelter = {
  id: "near-plain",
  name: "Near Plain",
  pos: [29.66, -82.32],
  special_needs: false,
  pet_friendly: false,
  height_above_river_m: 80,
};
const FAR_BOTH: Shelter = {
  id: "far-both",
  name: "Far Both",
  pos: [29.7, -82.32],
  special_needs: true,
  pet_friendly: true,
  height_above_river_m: 80,
};
const NEAREST_FLAGGED: Shelter = {
  id: "nearest-flagged",
  name: "Nearest Flagged",
  pos: [29.651, -82.32],
  special_needs: true,
  pet_friendly: false,
  height_above_river_m: 80,
};

// A square from lat 29.64 to 29.66 and lon -82.33 to -82.31, with a hole around the Home.
const SQUARE: [number, number][] = [
  [-82.33, 29.64],
  [-82.31, 29.64],
  [-82.31, 29.66],
  [-82.33, 29.66],
  [-82.33, 29.64],
];
const HOLE: [number, number][] = [
  [-82.322, 29.648],
  [-82.318, 29.648],
  [-82.318, 29.652],
  [-82.322, 29.652],
  [-82.322, 29.648],
];

function ridge(id: string, lat: number, climb: number): HighGroundPoint {
  return {
    id,
    name: `Ridge ${id}`,
    pos: [lat, -82.32],
    town: "Home",
    climb_m: climb,
    walk_minutes: 9,
  };
}
const NEAR_RIDGE = ridge("near", 29.66, 90);
const FAR_RIDGE = ridge("far", 29.665, 140);
const OUT_OF_RANGE_RIDGE = ridge("away", 29.68, 200);

function pack(overrides: Partial<CachePackContents> = {}): CachePackContents {
  return {
    shelters: [NEAR_PLAIN, FAR_BOTH, NEAREST_FLAGGED],
    highGround: [],
    floodProne: { features: [] },
    routeGrid: null,
    built: null,
    basemap: null,
    bbox: null,
    ...overrides,
  };
}

function profile(overrides: Partial<HouseholdProfile> = {}): HouseholdProfile {
  return {
    home: HOME,
    housing: "site-built",
    needsSpecialNeedsShelter: false,
    needsPetFriendlyShelter: false,
    ...overrides,
  };
}

function floodRisk(level: FloodRisk["level"]): FloodRisk {
  return {
    level,
    reasons: level ? [{ code: "water_high", nodes: 2, value: 55 }] : [],
    storm_signal: { on: false, nodes: 0, pressure_hpa: null },
    nodes: {},
    surged: [],
  };
}

function plan(overrides: Partial<Parameters<typeof evacuationPlan>[0]> = {}) {
  return evacuationPlan({
    profile: profile(),
    pack: pack(),
    openShelterIds: ["near-plain", "far-both", "nearest-flagged"],
    floodRisk: null,
    region: NEPAL_REGION,
    hazard: "flash_flood",
    routes: null,
    rerouting: null,
    officialAlerts: [],
    wave: null,
    ...overrides,
  });
}

test("closed Shelters are skipped", () => {
  const result = plan({ openShelterIds: ["near-plain", "far-both"] });
  expect(result.shelter).toBe(NEAR_PLAIN);
  expect(result.lines.join(" ")).toContain("Near Plain, 1.1 km away");
});

test("when the nearest Shelter closes the plan picks the next nearest", () => {
  const open = ["near-plain", "far-both", "nearest-flagged"];
  expect(plan({ openShelterIds: open }).shelter).toBe(NEAREST_FLAGGED);
  expect(plan({ openShelterIds: open.slice(0, 2) }).shelter).toBe(NEAR_PLAIN);
});

test("a household with no needs can get a Shelter flagged special-needs, and sees the flag", () => {
  const result = plan();
  expect(result.shelter).toBe(NEAREST_FLAGGED);
  expect(result.lines.join(" ")).toContain("(special-needs)");
});

test("special-needs and pet-friendly needs are required together", () => {
  expect(plan({ profile: profile({ needsSpecialNeedsShelter: true }) }).shelter).toBe(
    NEAREST_FLAGGED,
  );
  expect(plan({ profile: profile({ needsPetFriendlyShelter: true }) }).shelter).toBe(FAR_BOTH);
  const both = profile({ needsSpecialNeedsShelter: true, needsPetFriendlyShelter: true });
  expect(plan({ profile: both }).shelter).toBe(FAR_BOTH);
});

test("no Shelter listed open says so and marks nothing", () => {
  const result = plan({ openShelterIds: [] });
  expect(result.shelter).toBeNull();
  expect(result.lines).toContain("No open Shelter announced yet. Follow official sources.");
});

test("open Shelters that do not fit are never offered as partial matches", () => {
  const result = plan({
    profile: profile({ needsPetFriendlyShelter: true }),
    openShelterIds: ["near-plain", "nearest-flagged"],
  });
  expect(result.shelter).toBeNull();
  expect(result.lines).toContain(
    "No open Shelter matches this household. Follow official sources.",
  );
});

test("a home inside a Flood-Prone Area is flagged and one outside is not", () => {
  const floodProne = {
    features: [{ geometry: { type: "Polygon" as const, coordinates: [SQUARE] } }],
  };
  expect(plan({ pack: pack({ floodProne }) }).lines).toContain(
    "Your home is inside a mapped Flood-Prone Area.",
  );
  const elsewhere = profile({ home: { lat: 29.7, lon: -82.2 } });
  expect(plan({ pack: pack({ floodProne }), profile: elsewhere }).lines[0]).toMatch(
    /^Your home is outside the mapped Flood-Prone Areas/,
  );
});

test("a hole in a polygon and a MultiPolygon are respected", () => {
  const holed = {
    features: [{ geometry: { type: "Polygon" as const, coordinates: [SQUARE, HOLE] } }],
  };
  expect(plan({ pack: pack({ floodProne: holed }) }).lines[0]).toMatch(/^Your home is outside/);
  const multi = {
    features: [{ geometry: { type: "MultiPolygon" as const, coordinates: [[SQUARE]] } }],
  };
  expect(plan({ pack: pack({ floodProne: multi }) }).lines[0]).toMatch(/^Your home is inside/);
});

test("a null Flood Risk level leaves the risk section out", () => {
  expect(plan({ floodRisk: floodRisk(null) }).risk).toBeNull();
  expect(plan({ floodRisk: null }).risk).toBeNull();
  expect(plan({ floodRisk: floodRisk("elevated") }).risk).toEqual({
    level: "elevated",
    reasons: ["water level 55 cm at 2 Nodes"],
  });
});

test("no saved profile shows the headline and a prompt, with no area or Shelter lines", () => {
  const result = plan({ profile: null, floodRisk: floodRisk("high") });
  expect(result.risk?.level).toBe("high");
  expect(result.lines).toEqual([
    "Fill in your household profile to see your Flood-Prone Area and nearest Shelter.",
  ]);
  expect(result.shelter).toBeNull();
});

test("no valid Cache Pack yet says the information is loading", () => {
  const result = plan({ pack: null, floodRisk: floodRisk("low") });
  expect(result.risk?.level).toBe("low");
  expect(result.lines).toEqual([
    "Shelter and flood-area information is still loading on this Node. Follow official sources.",
  ]);
  expect(result.shelter).toBeNull();
});

test("the plan gives no evacuation instruction of its own", () => {
  const floodProne = {
    features: [{ geometry: { type: "Polygon" as const, coordinates: [SQUARE] } }],
  };
  const everyCase = [
    plan({ floodRisk: floodRisk("high"), pack: pack({ floodProne }) }),
    plan({ openShelterIds: [] }),
    plan({ profile: profile({ needsPetFriendlyShelter: true }), openShelterIds: ["near-plain"] }),
    plan({ profile: null }),
    plan({ pack: null }),
    plan({ routes: ROUTES }),
  ];
  const instructionVerbs =
    /\b(evacuate|leave|go|drive|head|move|travel|take|stay|shelter in place)\b/i;
  for (const result of everyCase) {
    expect(result.officialLine).toBe(OFFICIAL_LINE);
    const sentences = [...(result.risk?.reasons ?? []), ...result.lines];
    for (const sentence of sentences) expect(sentence).not.toMatch(instructionVerbs);
  }
});

// Routes start at the Grid point nearest HOME and end at their Shelter. NEAREST_FLAGGED is the
// closest in a straight line but its road runs a long way round.
const GRID_POINT: [number, number] = [29.6501, -82.3201];
const ROUTES: Routes = {
  "nearest-flagged": [GRID_POINT, [29.6501, -82.35], [29.651, -82.35], NEAREST_FLAGGED.pos],
  "near-plain": [GRID_POINT, [29.655, -82.3201], NEAR_PLAIN.pos],
  "far-both": [GRID_POINT, [29.68, -82.3201], FAR_BOTH.pos],
};

test("Shelters are ranked by road distance, not straight-line distance", () => {
  const result = plan({ routes: ROUTES });
  expect(result.shelter).toBe(NEAR_PLAIN);
  expect(result.lines.join(" ")).toMatch(/Near Plain, 1\.\d km by road/);
});

test("the route starts at the Grid point and ends at the chosen Shelter", () => {
  const result = plan({ routes: ROUTES });
  expect(result.route?.[0]).toEqual(GRID_POINT);
  expect(result.route?.at(-1)).toEqual(result.shelter?.pos);
});

test("a Shelter with no Route ranks after every Shelter that has one, and says so", () => {
  const result = plan({
    routes: { "nearest-flagged": ROUTES["nearest-flagged"], "far-both": ROUTES["far-both"] },
  });
  expect(result.shelter).toBe(FAR_BOTH);

  const onlyUnrouted = plan({ routes: {}, openShelterIds: ["near-plain"] });
  expect(onlyUnrouted.shelter).toBe(NEAR_PLAIN);
  expect(onlyUnrouted.route).toBeNull();
  expect(onlyUnrouted.lines.join(" ")).toContain(
    "Near Plain, 1.1 km away in a straight line, no road route available",
  );
});

// The builder drops a Route that crosses the Flood-Prone Area, so its Shelter is simply missing
// from the Grid point's file.
test("a Shelter whose Route the builder dropped gets no line, even beside one that has a Route", () => {
  const result = plan({
    routes: { "far-both": ROUTES["far-both"] },
    openShelterIds: ["near-plain", "far-both"],
  });
  expect(result.shelter).toBe(FAR_BOTH);
  expect(result.route).toEqual(ROUTES["far-both"]);

  const dropped = plan({
    routes: { "far-both": ROUTES["far-both"] },
    openShelterIds: ["near-plain"],
  });
  expect(dropped.route).toBeNull();
});

test("the plan says the route ignores flooding and road closures, only when it draws one", () => {
  const warning = "The route is the shortest by road and ignores flooding and road closures.";
  expect(plan({ routes: ROUTES }).lines).toContain(warning);
  expect(plan({ routes: null }).lines).not.toContain(warning);
});

test("no open Shelter draws no route", () => {
  expect(plan({ routes: ROUTES, openShelterIds: [] }).route).toBeNull();
});

const RIVERBANK_SMS: OfficialAlert = {
  id: "dhm-sms",
  source: "dhm",
  mode: "replay",
  issued: "2026-08-26T09:15:00+05:45",
  headline:
    "SMS to riverbank residents of Rasuwa, Nuwakot, Dhading and Chitwan: remain on high alert",
  applies_to: ["flood_prone_area"],
  url: "https://example.org/sms",
};
const FOR_EVERYONE: OfficialAlert = {
  ...RIVERBANK_SMS,
  id: "dhm-notice",
  issued: "2026-08-26T09:05:00+05:45",
  applies_to: [],
};
const FOR_MOBILE_HOMES: OfficialAlert = {
  ...RIVERBANK_SMS,
  id: "mobile",
  applies_to: ["mobile_home"],
};
const AROUND_HOME = {
  features: [{ geometry: { type: "Polygon" as const, coordinates: [SQUARE] } }],
};

test("a home in the Flood-Prone Area matches the riverbank alert; one outside does not", () => {
  const inside = plan({ pack: pack({ floodProne: AROUND_HOME }), officialAlerts: [RIVERBANK_SMS] });
  expect(inside.officialAlerts).toEqual([RIVERBANK_SMS]);
  const outside = plan({
    pack: pack({ floodProne: AROUND_HOME }),
    profile: profile({ home: { lat: 29.7, lon: -82.2 } }),
    officialAlerts: [RIVERBANK_SMS],
  });
  expect(outside.officialAlerts).toEqual([]);
});

test("an alert with no tags applies to every household, and housing tags match housing", () => {
  const alerts = [FOR_EVERYONE, FOR_MOBILE_HOMES];
  expect(plan({ officialAlerts: alerts }).officialAlerts).toEqual([FOR_EVERYONE]);
  const mobileHome = profile({ housing: "mobile-home-rv" });
  expect(plan({ officialAlerts: alerts, profile: mobileHome }).officialAlerts).toEqual(alerts);
});

test("with no Cache Pack yet the riverbank alert is still listed", () => {
  expect(plan({ pack: null, officialAlerts: [RIVERBANK_SMS] }).officialAlerts).toEqual([
    RIVERBANK_SMS,
  ]);
});

test("with no Official Alert there is no evacuation language", () => {
  const result = plan({ floodRisk: floodRisk("high"), pack: pack({ floodProne: AROUND_HOME }) });
  expect(result.officialAlerts).toEqual([]);
  const sentences = [...(result.risk?.reasons ?? []), ...result.lines];
  for (const sentence of sentences) expect(sentence).not.toMatch(/\bevacuat/i);
});

// Walking to NEAR_PLAIN (1.1 km straight) takes 24 min; to FAR_BOTH (5.6 km) 118 min.
const EVENT_T = 1_000_000;
const wave = (minutesAway: number) => ({
  arrivalAt: EVENT_T + minutesAway * 60,
  eventT: EVENT_T,
});

describe("with a Wave ETA", () => {
  test("a reachable Shelter is shown with the walk, the wave and its height", () => {
    const result = plan({ wave: wave(43), openShelterIds: ["near-plain"] });
    expect(result.shelter).toBe(NEAR_PLAIN);
    expect(result.lines.join(" ")).toContain("80 m above the river");
    expect(result.lines).toContain("24 min walk, wave in 43 min.");
  });

  test("a reachable Shelter with no Route is still offered, by its straight-line walk, with no line", () => {
    const result = plan({ wave: wave(43), openShelterIds: ["near-plain"], routes: {} });
    expect(result.shelter).toBe(NEAR_PLAIN);
    expect(result.route).toBeNull();
    expect(result.lines).toContain("24 min walk, wave in 43 min.");
  });

  test("a reachable Shelter beats a nearer one inside the Flood-Prone Area", () => {
    // Around NEAREST_FLAGGED (29.651) only.
    const ring: [number, number][] = [
      [-82.321, 29.6505],
      [-82.319, 29.6505],
      [-82.319, 29.6515],
      [-82.321, 29.6515],
      [-82.321, 29.6505],
    ];
    const floodProne = {
      features: [{ geometry: { type: "Polygon" as const, coordinates: [ring] } }],
    };
    const result = plan({
      wave: wave(60),
      pack: pack({ floodProne }),
      openShelterIds: ["near-plain", "nearest-flagged"],
    });
    expect(result.shelter).toBe(NEAR_PLAIN);
  });

  test("walking time plus the 5 min margin past the ETA means higher ground", () => {
    const tooLate = plan({ wave: wave(28), openShelterIds: ["near-plain"] });
    expect(tooLate.shelter).toBeNull();
    expect(tooLate.route).toBeNull();
    expect(tooLate.lines).toContain("Nearest Shelter Near Plain: 24 min walk, wave in 28 min.");
    expect(tooLate.lines).toContain(
      "No Shelter you can reach in time. Get to higher ground, away from the river, now.",
    );
    expect(plan({ wave: wave(29), openShelterIds: ["near-plain"] }).shelter).toBe(NEAR_PLAIN);
  });

  test("a Shelter out of reach in time is still given for the map, never as the chosen one", () => {
    const tooLate = plan({ wave: wave(28), openShelterIds: ["near-plain"] });
    expect(tooLate.shelter).toBeNull();
    expect(tooLate.outOfReachShelter).toBe(NEAR_PLAIN);
    expect(plan({ wave: wave(29), openShelterIds: ["near-plain"] }).outOfReachShelter).toBeNull();
    expect(plan({ wave: null, openShelterIds: ["near-plain"] }).outOfReachShelter).toBeNull();
  });

  describe("High-ground points", () => {
    const withRidges = pack({ highGround: [FAR_RIDGE, OUT_OF_RANGE_RIDGE, NEAR_RIDGE] });

    test("the climb line comes from fixed numbers", () => {
      expect(highGroundLabel(90, 11)).toBe("90 m up · 11 min walk");
    });

    test("with no Shelter reachable the plan names the nearest point and gives those within 2 km", () => {
      const tooLate = plan({ wave: wave(28), openShelterIds: ["near-plain"], pack: withRidges });
      expect(tooLate.highGround.map((pin) => [pin.point.id, pin.nearest])).toEqual([
        ["near", true],
        ["far", false],
      ]);
      // 0.01 degrees of latitude is 1.11 km: 24 minutes at the plan's walking speed, as for a Shelter.
      expect(tooLate.highGround[0].walkMinutes).toBe(24);
      expect(tooLate.lines).toContain("Nearest high ground: Ridge near, 90 m up · 24 min walk.");
    });

    test("they stay hidden while a Shelter can be reached, on a calm day and with no warning", () => {
      const reachable = plan({ wave: wave(29), openShelterIds: ["near-plain"], pack: withRidges });
      expect(reachable.highGround).toEqual([]);
      expect(
        plan({ wave: null, openShelterIds: ["near-plain"], pack: withRidges }).highGround,
      ).toEqual([]);
      expect(plan({ pack: withRidges }).highGround).toEqual([]);
    });

    test("a home with no point within 2 km keeps the generic higher-ground line", () => {
      const awayFromRidges = pack({ highGround: [OUT_OF_RANGE_RIDGE] });
      const tooLate = plan({
        wave: wave(28),
        openShelterIds: ["near-plain"],
        pack: awayFromRidges,
      });
      expect(tooLate.highGround).toEqual([]);
      expect(tooLate.lines.join(" ")).not.toContain("Nearest high ground");
      expect(tooLate.lines.join(" ")).toContain("Get to higher ground");
    });
  });

  test("the out-of-reach Shelter is the closest one outside the Flood-Prone Area", () => {
    const ring: [number, number][] = [
      [-82.321, 29.6505],
      [-82.319, 29.6505],
      [-82.319, 29.6515],
      [-82.321, 29.6515],
      [-82.321, 29.6505],
    ];
    const floodProne = {
      features: [{ geometry: { type: "Polygon" as const, coordinates: [ring] } }],
    };
    const both = plan({
      wave: wave(1),
      pack: pack({ floodProne }),
      openShelterIds: ["near-plain", "nearest-flagged"],
    });
    expect(both.outOfReachShelter).toBe(NEAR_PLAIN);
    expect(both.lines).toContain("Nearest Shelter Near Plain: 24 min walk, wave in 1 min.");

    const onlyFlagged = plan({
      wave: wave(1),
      pack: pack({ floodProne }),
      openShelterIds: ["nearest-flagged"],
    });
    expect(onlyFlagged.outOfReachShelter).toBeNull();
    expect(onlyFlagged.lines.join(" ")).toContain("Nearest Shelter");
  });

  test("at the arrival time it is always higher ground", () => {
    const result = plan({ wave: wave(0), openShelterIds: ["near-plain"] });
    expect(result.lines).toContain("Nearest Shelter Near Plain: 24 min walk, wave expected now.");
    expect(result.shelter).toBeNull();
  });

  test("closed Shelters are skipped", () => {
    const result = plan({ wave: wave(60), openShelterIds: ["far-both"] });
    expect(result.shelter).toBeNull();
    expect(result.lines.join(" ")).toContain("Nearest Shelter Far Both");
  });

  test("a reachable Shelter that does not fit loses to higher ground", () => {
    const result = plan({
      wave: wave(60),
      profile: profile({ needsPetFriendlyShelter: true }),
      openShelterIds: ["near-plain", "far-both"],
    });
    expect(result.shelter).toBeNull();
    expect(result.lines.join(" ")).toContain("Nearest Shelter Far Both");
  });

  test("higher ground still carries the area line and the official sources line", () => {
    const result = plan({ wave: wave(1), openShelterIds: ["near-plain"] });
    expect(result.lines[0]).toContain("Flood-Prone Area");
    expect(result.officialLine).toBe(OFFICIAL_LINE);
  });

  test("with no open Shelter the plan keeps its own message", () => {
    const result = plan({ wave: wave(60), openShelterIds: [] });
    expect(result.lines).toContain("No open Shelter announced yet. Follow official sources.");
  });

  test("higher ground never sends anyone to a basement or towards the river", () => {
    const result = plan({ wave: wave(1), openShelterIds: ["near-plain"] });
    expect(result.lines.join(" ")).not.toMatch(
      /basement|towards the river|toward the river|evacuate|must leave/i,
    );
    expect(result.officialLine).toBe(OFFICIAL_LINE);
  });

  test("with no wave the plan is as before", () => {
    const result = plan({ wave: null, openShelterIds: ["near-plain"] });
    expect(result.lines.join(" ")).not.toContain("min walk");
    expect(result.lines.join(" ")).not.toContain("above the river");
  });
});

describe("on a coast", () => {
  const coastShelter = (id: string, lat: number): Shelter => ({
    id,
    name: id,
    pos: [lat, -82.32],
    special_needs: false,
    pet_friendly: false,
  });
  const low = coastShelter("low", 29.651);
  const high = coastShelter("high", 29.66);
  // The ring lies around `low` (29.651) only.
  const lowGround = {
    features: [
      {
        geometry: {
          type: "Polygon" as const,
          coordinates: [
            [
              [-82.321, 29.6505],
              [-82.319, 29.6505],
              [-82.319, 29.6515],
              [-82.321, 29.6515],
              [-82.321, 29.6505],
            ] as [number, number][],
          ],
        },
      },
    ],
  };
  const coastPlan = (overrides: Partial<Parameters<typeof evacuationPlan>[0]> = {}) =>
    plan({
      region: FAKE_REGION,
      hazard: "storm_surge",
      pack: pack({ shelters: [low, high], floodProne: lowGround }),
      openShelterIds: ["low", "high"],
      ...overrides,
    });

  test("a Shelter inside the Flood-Prone Area is not offered, even with no Water ETA", () => {
    expect(coastPlan().shelter).toBe(high);
    expect(coastPlan({ openShelterIds: ["low"] }).shelter).toBeNull();
    expect(coastPlan({ openShelterIds: ["low"] }).lines).toContain(
      "No open Shelter outside the Flood-Prone Area. Follow official sources.",
    );
  });

  test("the Water ETA sets which Shelters can be reached in time", () => {
    // `high` is 1.1 km away: a 24 min walk.
    expect(coastPlan({ wave: wave(60) }).shelter).toBe(high);
    const tooLate = coastPlan({ wave: wave(28) });
    expect(tooLate.shelter).toBeNull();
    expect(tooLate.outOfReachShelter).toBe(high);
    expect(tooLate.lines.join(" ")).not.toContain("low");
  });

  test("speaks of the water, not a wave or a river", () => {
    const tooLate = coastPlan({ wave: wave(28) });
    expect(tooLate.lines).toContain("Nearest Shelter high: 24 min walk, water in 28 min.");
    expect(tooLate.lines).toContain(
      "No Shelter you can reach in time. Get to higher ground, away from the water, now.",
    );
    const now = coastPlan({ wave: wave(0) });
    expect(now.lines).toContain("Nearest Shelter high: 24 min walk, water expected now.");
    expect(coastPlan({ wave: wave(60) }).lines.join(" ")).toContain(
      "24 min walk, water in 60 min.",
    );
    expect(tooLate.lines.join(" ")).not.toMatch(/wave|river/);
  });
});
