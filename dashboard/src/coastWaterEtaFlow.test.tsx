import { act, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";
import { expandPanel } from "./expandPanel";
import { BASEMAP_MANIFEST_PARTS } from "./fakeBasemap";
import { NEPAL_REGION, FAKE_REGION, fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import { STATE_POLL_MS } from "./useNodeState";

const PROFILE_KEY = "storm-shield.household-profile";
const HOME = { lat: 26.45, lon: -81.95 };
const T = 1_664_000_000;

// The home's ground: 1.5 m above the datum, one Terrarium pixel (32768 + 1.5 = 128 * 256 + 1 + 128/256).
const GROUND_PIXEL = [128, 1, 128, 255];

let eventT: number;
// What the shore Sensor reports, in metres; null for a Sensor with no water gauge reading.
let levelM: number | null;
let region: typeof FAKE_REGION;
let elevationRequests: string[];

function stubNode() {
  vi.stubGlobal("createImageBitmap", async () => ({ width: 1, height: 1 }));
  vi.stubGlobal(
    "OffscreenCanvas",
    class {
      getContext() {
        return {
          drawImage() {},
          getImageData: () => ({ width: 1, height: 1, data: new Uint8ClampedArray(GROUND_PIXEL) }),
        };
      }
    },
  );
  vi.stubGlobal("fetch", async (url: string) => {
    if (url === "/api/state") {
      return Response.json(
        fakeNodeState({
          id: "shore",
          role: "sensor",
          region,
          hazard: region.water_type === "coast" ? "storm_surge" : "flash_flood",
          nodes: [
            fakeNodeSnapshot("shore", {
              position: [HOME.lat, HOME.lon],
              measurements: levelM === null ? {} : { water_level: { value: levelM, unit: "m" } },
            }),
          ],
        }),
      );
    }
    if (url === "/api/replay") {
      return Response.json({ v: 1, kind: "replay", state: "paused", event_t: eventT, rate: 30 });
    }
    if (url === "/api/cache-pack") {
      return Response.json({
        available: true,
        manifest: {
          built: "2026-10-18T12:00:00+00:00",
          bbox: [26.3, -82, 26.67, -81.75],
          ...BASEMAP_MANIFEST_PARTS,
        },
      });
    }
    if (url === "/api/shelters") return Response.json({ open: [] });
    if (url === "/api/cache-pack/files/shelters.json") return Response.json([]);
    if (url === "/api/cache-pack/files/flood_prone.geojson") {
      return Response.json({ type: "FeatureCollection", features: [] });
    }
    if (url.startsWith("/api/cache-pack/files/elevation/")) {
      elevationRequests.push(url);
      // A string body: jsdom's Blob has no stream(), which Node 22's Response needs.
      return new Response("tile");
    }
    return new Response(null, { status: 404 });
  });
}

// The Node's next answers: the Event clock moves to `at` and the Sensor reads `metres`.
async function hear(at: number, metres: number | null) {
  eventT = at;
  levelM = metres;
  await act(() => vi.advanceTimersByTimeAsync(STATE_POLL_MS));
}

beforeEach(() => {
  eventT = T;
  levelM = 0.5;
  region = FAKE_REGION;
  elevationRequests = [];
  localStorage.setItem(
    PROFILE_KEY,
    JSON.stringify({
      version: 1,
      profile: {
        home: HOME,
        housing: "site-built",
        needsSpecialNeedsShelter: false,
        needsPetFriendlyShelter: false,
      },
    }),
  );
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.useFakeTimers({ shouldAdvanceTime: true });
  stubNode();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openPlan() {
  render(<App />);
  // The first poll must be heard before the test moves the clock, or a slow machine hears only the
  // second reading and there is no rate yet.
  await screen.findByText("porch");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Expand Evacuation Plan" })).toBeVisible(),
  );
  expandPanel("Evacuation Plan");
}

const ETA = /^Water reaches your ground in about/;

test("the Water ETA is worked out from the home's ground, the level and its rate of rise", async () => {
  await openPlan();
  await waitFor(() => expect(elevationRequests).not.toHaveLength(0));
  // One reading has no rate yet.
  expect(screen.queryByText(ETA)).not.toBeInTheDocument();

  await hear(T + 900, 0.6);
  // 0.9 m of gap at 0.4 m an hour: 2 h 15 min.
  expect(await screen.findByText(/Water reaches your ground in about 2 h 15 min/)).toBeVisible();
  expect(screen.getByText("level 2 ft, rising 1.3 ft/h, your ground 4.9 ft")).toBeVisible();
});

test("the ETA is judged again as each reading arrives", async () => {
  await openPlan();
  await hear(T + 900, 0.6);
  await screen.findByText(/in about 2 h 15 min/);

  await hear(T + 1800, 0.8);
  // A faster rise: 0.7 m of gap at 0.8 m an hour is 52.5 min.
  expect(await screen.findByText(/in about 53 min/)).toBeVisible();
});

test("it counts down on the Event clock between readings", async () => {
  await openPlan();
  await hear(T + 900, 0.6);
  await screen.findByText(/in about 2 h 15 min/);

  await hear(T + 900 + 600, 0.6);
  expect(await screen.findByText(/in about 2 h 5 min/)).toBeVisible();
});

test("it says the water is at the ground once the level reaches it", async () => {
  await openPlan();
  await hear(T + 900, 0.6);
  await hear(T + 1800, 1.5);
  expect(await screen.findByText(/Water is at your ground now/)).toBeVisible();
  expect(screen.queryByText(ETA)).not.toBeInTheDocument();
});

test("there is none while the level falls", async () => {
  await openPlan();
  await hear(T + 900, 0.6);
  await screen.findByText(ETA);

  await hear(T + 1800, 0.5);
  await waitFor(() => expect(screen.queryByText(ETA)).not.toBeInTheDocument());
});

test("there is none when no Node reports a water level", async () => {
  levelM = null;
  await openPlan();
  await hear(T + 900, null);
  await hear(T + 1800, null);
  expect(screen.queryByText(ETA)).not.toBeInTheDocument();
});

test("a river Region gets no coast ETA and reads no terrain", async () => {
  region = { ...NEPAL_REGION } as typeof FAKE_REGION;
  await openPlan();
  await hear(T + 900, 0.6);
  await hear(T + 1800, 0.8);
  expect(screen.queryByText(ETA)).not.toBeInTheDocument();
  expect(elevationRequests).toEqual([]);
});
