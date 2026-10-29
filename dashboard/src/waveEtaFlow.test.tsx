import { render, screen, waitFor, within } from "@testing-library/react";
import { BASEMAP_MANIFEST_PARTS } from "./fakeBasemap";

import { App } from "./App";
import type { CommunityWarning, FlashFloodWarning } from "./communityWarnings";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { sourceData } from "./fakeMaplibre";

const PROFILE_KEY = "storm-shield.household-profile";
const SURGE_T = 1_787_716_020;

// A straight river at lon 85, one vertex every 10 km (0.09 degrees of latitude): 190 km/h down to
// km 0, then 60 km/h. From km -10 the wave takes 189.5 s + 20 min to reach km 20: 1389.5 s.
const RIVER = {
  features: [
    {
      properties: { speed_kmh: 190, km: [-10, 0] },
      geometry: {
        coordinates: [
          [85, 28.09],
          [85, 28],
        ],
      },
    },
    {
      properties: { speed_kmh: 60, km: [0, 10, 20, 30] },
      geometry: {
        coordinates: [
          [85, 28],
          [85, 27.91],
          [85, 27.82],
          [85, 27.73],
        ],
      },
    },
  ],
};

const NEPAL_MANIFEST = {
  built: "2026-10-18T12:00:00+00:00",
  bbox: [27.7, 84.9, 28.1, 85.1],
  ...BASEMAP_MANIFEST_PARTS,
};

const WARNING: FlashFloodWarning = {
  id: 7,
  t: SURGE_T + 3,
  nodes: ["s0"],
  hazard: "flash_flood",
  reasons: ["water_surge"],
  origin: "s0",
  origin_km: -10,
  surge_t: SURGE_T,
};

const KM_20 = { lat: 27.82, lon: 85 };
const KM_MINUS_5 = { lat: 28.045, lon: 85 };

function saveProfile(home: { lat: number; lon: number }) {
  localStorage.setItem(
    PROFILE_KEY,
    JSON.stringify({
      version: 1,
      profile: {
        home,
        housing: "site-built",
        needsSpecialNeedsShelter: false,
        needsPetFriendlyShelter: false,
      },
    }),
  );
}

let requests: string[];

function shelterAt(lat: number) {
  return {
    id: "gompa",
    name: "Gompa",
    pos: [lat, 85],
    special_needs: false,
    pet_friendly: false,
    height_above_river_m: 66,
  };
}

function stubNode({
  eventT,
  river = RIVER,
  warning = WARNING,
  shelters = [],
  town = null,
  highGround = [],
}: {
  eventT: number;
  river?: object | null;
  warning?: CommunityWarning;
  shelters?: object[];
  // A place at the home, so the corner card has a town to name.
  town?: string | null;
  highGround?: object[];
}) {
  const answers: Record<string, unknown> = {
    "/api/state": nepalNodeState({
      id: "porch",
      role: "sensor",
      community_warnings: [warning],
      nodes: [fakeNodeSnapshot("porch", { river_km: 20, position: [KM_20.lat, KM_20.lon] })],
    }),
    "/api/replay": { v: 1, kind: "replay", state: "paused", event_t: eventT, rate: 30 },
    "/api/cache-pack": {
      available: true,
      manifest:
        town || highGround.length > 0
          ? {
              ...(town ? NEPAL_MANIFEST : {}),
              files: {
                ...(town ? BASEMAP_MANIFEST_PARTS.files : {}),
                ...(highGround.length > 0 ? { "high_ground.json": "sha" } : {}),
              },
            }
          : null,
    },
    "/api/cache-pack/files/high_ground.json": highGround,
    "/api/cache-pack/files/basemap/places.geojson": {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { name: town, kind: "town" },
          geometry: { type: "Point", coordinates: [KM_20.lon, KM_20.lat] },
        },
      ],
    },
    "/api/shelters": { open: shelters.map((shelter) => (shelter as { id: string }).id) },
    "/api/cache-pack/files/shelters.json": shelters,
    "/api/cache-pack/files/flood_prone.geojson": { type: "FeatureCollection", features: [] },
    "/api/cache-pack/files/river.geojson": river,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push(JSON.stringify([url, init ?? null]));
      return answers[url] ? Response.json(answers[url]) : new Response(null, { status: 404 });
    }),
  );
}

beforeEach(() => {
  localStorage.clear();
  requests = [];
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("the plan and the warning card count down to the wave at the home in the profile", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60 });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(await within(plan).findByText("Wave expected at your home in about 23 min")).toBeVisible();
  const card = screen.getByRole("article", { name: "Community Warning" });
  expect(within(card).getByText("Wave expected at your home in about 23 min")).toBeVisible();
});

test("with no profile the connected Node's position is the home", async () => {
  stubNode({ eventT: SURGE_T + 60 });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(await within(plan).findByText("Wave expected at your home in about 23 min")).toBeVisible();
});

test("at or past the arrival time it says the wave is expected now", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 3000 });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(await within(plan).findByText("Wave expected now")).toBeVisible();
});

test("a home upstream of the origin gets no ETA", async () => {
  saveProfile(KM_MINUS_5);
  stubNode({ eventT: SURGE_T + 60 });
  render(<App />);

  await screen.findByRole("article", { name: "Community Warning" });
  await waitFor(() => expect(requests.join()).toContain("river.geojson"));
  expect(screen.queryByText(/Wave expected/)).toBeNull();
});

test("a pack with no river line gives no ETA and no error", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60, river: null });
  render(<App />);

  await screen.findByRole("article", { name: "Community Warning" });
  await waitFor(() => expect(requests.join()).toContain("river.geojson"));
  expect(screen.queryByText(/Wave expected/)).toBeNull();
  expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain("river");
});

test("no request carries the home location", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60 });
  render(<App />);

  await screen.findByText("Wave expected at your home in about 23 min", {
    selector: "section[aria-label='Evacuation Plan'] p",
  });
  expect(requests.filter((url) => url.includes("27.82") || url.includes("85"))).toEqual([]);
});

test("a measured speed moves the ETA and the warning card shows the arithmetic", async () => {
  saveProfile(KM_20);
  // 20 km in 1000 s between the Nodes; the wave then covers km 10 to 20 at 120 km/h (300 s).
  const measured = { node: "s1", km: 10, surge_t: SURGE_T + 1000, speed_kmh: 120 };
  stubNode({ eventT: SURGE_T + 60, warning: { ...WARNING, measured } });
  render(<App />);

  const card = await screen.findByRole("article", { name: "Community Warning" });
  expect(within(card).getByText("Measured: 20.0 km in 17 min = 120 km/h (s0 to s1)")).toBeVisible();
  expect(await within(card).findByText("Wave expected at your home in about 21 min")).toBeVisible();
});

// From KM_20 the wave is 23 min away at SURGE_T + 60. 0.004 degrees of latitude is a 10 min walk,
// 0.01 degrees a 24 min one.
test("a Shelter the resident can walk to before the wave is named with the walk and its height", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60, shelters: [shelterAt(27.824)] });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(await within(plan).findByText("10 min walk, wave in 23 min.")).toBeVisible();
  expect(within(plan).getByText(/Gompa.*66 m above the river/)).toBeVisible();
});

test("a Shelter the resident cannot reach in time becomes higher ground", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60, shelters: [shelterAt(27.83)] });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(
    await within(plan).findByText(
      "No Shelter you can reach in time. Get to higher ground, away from the river, now.",
    ),
  ).toBeVisible();
  await waitFor(() =>
    expect(document.querySelectorAll(".shelter-marker.out-of-reach")).toHaveLength(1),
  );
  expect(sourceData("route").features).toHaveLength(0);
  await waitFor(() => expect(sourceData("out-of-reach-line").features).toHaveLength(1));
});

function ridgeAt(id: string, lat: number) {
  return { id, name: `Ridge ${id}`, pos: [lat, 85], town: "Home", climb_m: 90, walk_minutes: 11 };
}

test("with no Shelter in reach the nearest High-ground point is outlined and the rest are shown", async () => {
  saveProfile(KM_20);
  stubNode({
    eventT: SURGE_T + 60,
    shelters: [shelterAt(27.83)],
    highGround: [ridgeAt("far", 27.835), ridgeAt("near", 27.825)],
  });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  expect(
    await within(plan).findByText(/Nearest high ground: Ridge near, 90 m up · \d+ min walk\./),
  ).toBeVisible();
  await waitFor(() => expect(document.querySelectorAll(".high-ground-pin")).toHaveLength(2));
  expect(document.querySelectorAll(".high-ground-pin.nearest")).toHaveLength(1);
  expect(document.querySelector(".high-ground-pin.nearest")).toHaveTextContent(
    /90 m up · \d+ min walk/,
  );
});

test("High-ground points stay off the map while a Shelter can be reached", async () => {
  saveProfile(KM_20);
  stubNode({
    eventT: SURGE_T + 60,
    shelters: [shelterAt(27.824)],
    highGround: [ridgeAt("near", 27.825)],
  });
  render(<App />);

  const plan = await screen.findByRole("region", { name: "Evacuation Plan" });
  await within(plan).findByText("10 min walk, wave in 23 min.");
  expect(document.querySelector(".high-ground-pin")).toBeNull();
});

test("the corner card names the town and shows the plan's minutes", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 60, town: "Betrawati" });
  render(<App />);

  const card = await screen.findByRole("complementary", { name: "Wave ETA" });
  expect(await within(card).findByText("MIN · Betrawati")).toBeVisible();
  expect(within(card).getByText("23")).toBeVisible();
});

test("past the arrival time the corner card says the wave is expected now", async () => {
  saveProfile(KM_20);
  stubNode({ eventT: SURGE_T + 3000, town: "Betrawati" });
  render(<App />);

  const card = await screen.findByRole("complementary", { name: "Wave ETA" });
  expect(within(card).getByText("wave expected now")).toBeVisible();
});

test("a home with no Wave ETA gets no corner card", async () => {
  saveProfile(KM_MINUS_5);
  stubNode({ eventT: SURGE_T + 60 });
  render(<App />);

  await screen.findByRole("article", { name: "Community Warning" });
  await waitFor(() => expect(requests.join()).toContain("river.geojson"));
  expect(screen.queryByRole("complementary", { name: "Wave ETA" })).toBeNull();
});
