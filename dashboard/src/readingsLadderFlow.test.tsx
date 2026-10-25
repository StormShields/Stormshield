import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";

const SURGE_T = 1_787_716_020;

// From km -10 at 190 km/h, then 60 km/h from km 0: 400 s after the Surge the front is at km 3.5.
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

const WARNING: CommunityWarning = {
  id: 7,
  t: SURGE_T + 3,
  nodes: ["s0"],
  hazard: "flash_flood",
  reasons: ["water_surge"],
  origin: "s0",
  origin_km: -10,
  surge_t: SURGE_T,
};

function stubNode(nodes: ReturnType<typeof fakeNodeSnapshot>[], eventT = SURGE_T + 400) {
  const answers: Record<string, unknown> = {
    "/api/state": fakeNodeState({
      id: "hub",
      name: "hub",
      role: "hub",
      nodes,
      community_warnings: [WARNING],
    }),
    "/api/replay": { v: 1, kind: "replay", state: "paused", event_t: eventT, rate: 30 },
    "/api/cache-pack": { available: true, manifest: null },
    "/api/shelters": { open: [] },
    "/api/cache-pack/files/shelters.json": [],
    "/api/cache-pack/files/flood_prone.geojson": { type: "FeatureCollection", features: [] },
    "/api/cache-pack/files/river.geojson": RIVER,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      answers[url] ? Response.json(answers[url]) : new Response(null, { status: 404 }),
    ),
  );
}

const water = (cm: number) => ({ water_level: { value: cm / 100, unit: "m" } });
const NODES = [
  fakeNodeSnapshot("s2", { name: "S2 Betrawati", river_km: 20, measurements: water(210) }),
  fakeNodeSnapshot("hub", { name: "hub", simulated: false }),
  fakeNodeSnapshot("s0", { name: "S0 Lhende", river_km: -10, measurements: water(95) }),
  fakeNodeSnapshot("pi", {
    name: "pi-table",
    simulated: false,
    measurements: { ...water(40), air_pressure: { value: 1009, unit: "hPa" } },
  }),
  fakeNodeSnapshot("s1", { name: "S1 Timure", river_km: 0, measurements: water(120) }),
];

const markers = () => [...document.querySelectorAll<HTMLElement>(".node-marker")];
const markerOf = (name: string) => markers().find((each) => within(each).queryByText(name));
const cardLabels = () =>
  [...document.querySelectorAll("section[aria-label^='Node ']")].map((each) =>
    each.getAttribute("aria-label"),
  );

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("the Pi is pinned first, the valley follows in River km order, the rest sit under the ladder", async () => {
  stubNode(NODES);
  render(<App />);

  const readings = await screen.findByRole("region", { name: "Readings" });
  await within(readings).findByRole("region", { name: "Node S0 Lhende" });
  expect(cardLabels()).toEqual([
    "Node pi-table",
    "Node S0 Lhende",
    "Node S1 Timure",
    "Node S2 Betrawati",
    "Node hub",
  ]);
  const pi = within(readings).getByRole("region", { name: "Node pi-table" });
  expect(within(pi).getByText("LIVE SENSORS")).toBeVisible();
  expect(within(pi).getByText("Pressure: 1009 hPa")).toBeVisible();
  expect(within(readings).getByText("120 cm")).toBeVisible();
});

test("the wave front is marked between the rungs it is passing", async () => {
  stubNode(NODES);
  render(<App />);

  const front = await screen.findByText("Wave front · km 4");
  const ladder = screen.getByRole("list", { name: "Valley Nodes by River km" });
  const order = [...ladder.children].map((each) => each.textContent);
  const at = order.findIndex((text) => text?.includes("Wave front"));
  expect(order[at - 1]).toContain("S1 Timure");
  expect(order[at + 1]).toContain("S2 Betrawati");
  expect(front).toBeVisible();
});

test("a Stale rung says how old it is and strikes its last water level through", async () => {
  stubNode(NODES.map((each) => (each.id === "s1" ? { ...each, stale: true, age_s: 40 } : each)));
  render(<App />);

  const rung = await screen.findByRole("region", { name: "Node S1 Timure" });
  expect(within(rung).getByText("STALE · 40 s")).toBeVisible();
  expect(within(rung).getByText("120 cm")).toHaveClass("struck");
});

test("selecting a valley Node on the map highlights its rung, and a rung highlights its marker", async () => {
  stubNode(NODES);
  render(<App />);
  await waitFor(() => expect(markerOf("S1 Timure")).toBeDefined());

  fireEvent.click(markerOf("S1 Timure")!);
  expect(screen.getByRole("region", { name: "Node S1 Timure" })).toHaveAttribute(
    "aria-current",
    "true",
  );

  fireEvent.click(screen.getByRole("region", { name: "Node S2 Betrawati" }));
  expect(markerOf("S2 Betrawati")).toHaveClass("selected");
  expect(markerOf("S1 Timure")).not.toHaveClass("selected");
});
