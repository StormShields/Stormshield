import { render, screen, waitFor } from "@testing-library/react";
import { BASEMAP_MANIFEST_PARTS } from "./fakeBasemap";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { lastMap, sourceData } from "./fakeMaplibre";
import { fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import { setReducedMotion } from "./fakeViewport";
import { waterReaches } from "./risingWater";

const SURGE_T = 1_787_716_020;

const RIVER_FEATURES = {
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

const RIVER = RIVER_FEATURES.features.map((feature) => ({
  speedKmh: feature.properties.speed_kmh,
  km: feature.properties.km,
  points: feature.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]),
}));

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

// 10 km at 190 km/h, then 20 km at 60 km/h.
const ARRIVES_AT = SURGE_T + (10 / 190) * 3600 + (20 / 60) * 3600;

describe("waterReaches", () => {
  const sensor = { riverKm: 20, waterLevelCm: 450 };

  it("draws nothing before a warning", () => {
    expect(waterReaches(RIVER, [], [sensor], SURGE_T + 9999)).toEqual([]);
  });

  it("draws nothing at a Node the wave has not reached", () => {
    expect(waterReaches(RIVER, [WARNING], [sensor], ARRIVES_AT - 60)).toEqual([]);
  });

  it("draws a dashed line either side and a rung per whole metre once it has", () => {
    const [reach] = waterReaches(RIVER, [WARNING], [sensor], ARRIVES_AT + 1);
    expect(reach.levelM).toBe(4.5);
    expect(reach.lines).toHaveLength(2);
    expect(reach.ticks).toHaveLength(8);
  });

  it("keeps the origin Node's own level, since the wave starts there", () => {
    const origin = { riverKm: -10, waterLevelCm: 750 };
    expect(waterReaches(RIVER, [WARNING], [origin], SURGE_T)).toHaveLength(1);
  });

  it("skips a Node off the river or with no water reading", () => {
    const off = [
      { riverKm: null, waterLevelCm: 400 },
      { riverKm: 20, waterLevelCm: null },
    ];
    expect(waterReaches(RIVER, [WARNING], off, ARRIVES_AT + 1)).toEqual([]);
  });
});

function stubNode(eventT: number) {
  const answers: Record<string, unknown> = {
    "/api/state": fakeNodeState({
      id: "porch",
      role: "sensor",
      community_warnings: [WARNING],
      nodes: [
        fakeNodeSnapshot("porch", {
          river_km: 20,
          position: [27.82, 85],
          measurements: { water_level: { value: 4.5, unit: "m" } },
        }),
      ],
    }),
    "/api/replay": { v: 1, kind: "replay", state: "paused", event_t: eventT, rate: 30 },
    "/api/cache-pack": {
      available: true,
      manifest: {
        built: "2026-10-18T12:00:00+00:00",
        bbox: [27.7, 84.9, 28.1, 85.1],
        ...BASEMAP_MANIFEST_PARTS,
      },
    },
    "/api/shelters": { open: [] },
    "/api/cache-pack/files/shelters.json": [],
    "/api/cache-pack/files/flood_prone.geojson": { type: "FeatureCollection", features: [] },
    "/api/cache-pack/files/river.geojson": RIVER_FEATURES,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      answers[url] ? Response.json(answers[url]) : new Response(null, { status: 404 }),
    ),
  );
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("the rising water on the map", () => {
  it("draws the height line, labels it RECONSTRUCTION and says so in the status strip", async () => {
    stubNode(ARRIVES_AT + 30);
    const { container } = render(<App />);
    await waitFor(() => expect(sourceData("water-level").features).toHaveLength(2));
    expect(sourceData("water-ticks").features).toHaveLength(8);
    expect(container.querySelector(".water-reconstruction")).toHaveTextContent("RECONSTRUCTION");
    expect(screen.getByText("Water level: RECONSTRUCTION")).toBeInTheDocument();
    expect(lastMap().getLayer("water-level")).toBeDefined();
  });

  it("draws nothing, and says nothing, before the wave reaches the Node", async () => {
    stubNode(ARRIVES_AT - 600);
    const { container } = render(<App />);
    await screen.findByRole("region", { name: "Map" });
    await waitFor(() => expect(lastMap().getLayer("river-flow")).toBeDefined());
    expect(sourceData("water-level").features).toHaveLength(0);
    expect(container.querySelector(".water-reconstruction")).toBeNull();
    expect(screen.queryByText("Water level: RECONSTRUCTION")).toBeNull();
  });

  it("is still a marked height with reduced motion", async () => {
    setReducedMotion(true);
    stubNode(ARRIVES_AT + 30);
    const { container } = render(<App />);
    await waitFor(() => expect(sourceData("water-level").features).toHaveLength(2));
    expect(container.querySelector(".water-reconstruction")).not.toBeNull();
  });
});
