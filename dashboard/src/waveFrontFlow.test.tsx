import { render, screen, waitFor } from "@testing-library/react";
import { BASEMAP_MANIFEST_PARTS } from "./fakeBasemap";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { lastMap, sourceData } from "./fakeMaplibre";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { setReducedMotion } from "./fakeViewport";
import { regionClockTime } from "./regionTime";

const SURGE_T = 1_787_716_020;
// From km -10: 189.5 s at 190 km/h to km 0, then 20 km at 60 km/h to Betrawati at km 20.
const ARRIVES_AT = SURGE_T + (10 / 190) * 3600 + (20 / 60) * 3600;

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

const MANIFEST = {
  built: "2026-10-18T12:00:00+00:00",
  bbox: [27.7, 84.9, 28.1, 85.1],
  ...BASEMAP_MANIFEST_PARTS,
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

function stubNode({
  eventT,
  warnings = [WARNING],
  state = "paused",
}: {
  eventT: number;
  warnings?: CommunityWarning[];
  state?: "paused" | "playing";
}) {
  const answers: Record<string, unknown> = {
    "/api/state": nepalNodeState({
      id: "porch",
      role: "sensor",
      community_warnings: warnings,
      nodes: [fakeNodeSnapshot("porch", { river_km: 20, position: [27.82, 85] })],
    }),
    "/api/replay": { v: 1, kind: "replay", state, event_t: eventT, rate: 30 },
    "/api/cache-pack": { available: true, manifest: MANIFEST },
    "/api/cache-pack/files/basemap/places.geojson": {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { name: "Betrawati", kind: "town", key: true },
          geometry: { type: "Point", coordinates: [85, 27.82] },
        },
      ],
    },
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

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

const features = (name: string) => sourceData(name).features.length;

describe("the wave front on the map", () => {
  it("shows a comet and its trail once a Surge exists, and nothing before", async () => {
    stubNode({ eventT: SURGE_T + 60 });
    render(<App />);
    await waitFor(() => expect(features("wave-head")).toBe(1));
    expect(features("wave-trail")).toBe(1);
  });

  it("draws nothing, and starts no animation, before any Surge", async () => {
    const frames = vi.spyOn(window, "requestAnimationFrame");
    stubNode({ eventT: SURGE_T + 60, warnings: [], state: "playing" });
    render(<App />);
    await screen.findByRole("region", { name: "Map" });
    await waitFor(() => expect(lastMap().getLayer("river-flow")).toBeDefined());
    expect(features("wave-head")).toBe(0);
    expect(features("wave-trail")).toBe(0);
    expect(frames).not.toHaveBeenCalled();
  });

  it("glides between clock answers while the replay plays", async () => {
    const frames = vi.spyOn(window, "requestAnimationFrame");
    stubNode({ eventT: SURGE_T + 60, state: "playing" });
    render(<App />);
    await waitFor(() => expect(frames).toHaveBeenCalled());
  });

  it("lights a Node for two event minutes after the front passes it, then lets it go", async () => {
    stubNode({ eventT: ARRIVES_AT + 30 });
    const { container, unmount } = render(<App />);
    await waitFor(() => expect(container.querySelector(".node-marker.wave-passed")).not.toBeNull());
    unmount();

    stubNode({ eventT: ARRIVES_AT + 200 });
    const later = render(<App />);
    await screen.findByRole("region", { name: "Map" });
    await waitFor(() => expect(features("wave-head")).toBe(1));
    expect(later.container.querySelector(".node-marker.wave-passed")).toBeNull();
  });

  it("lights a town when the front arrives and keeps its arrival time", async () => {
    stubNode({ eventT: ARRIVES_AT - 60 });
    const before = render(<App />);
    await waitFor(() => expect(before.container.querySelector(".place-label")).not.toBeNull());
    expect(before.container.querySelector(".wave-reached")).toBeNull();
    before.unmount();

    stubNode({ eventT: ARRIVES_AT + 6000 });
    const after = render(<App />);
    const stamp = await screen.findByText(
      `Betrawati ${regionClockTime(ARRIVES_AT, "Asia/Kathmandu")}`,
    );
    expect(stamp.closest(".place-label")).toHaveClass("wave-reached");
    after.unmount();
  });
});

describe("ambient river flow", () => {
  const visibility = () => lastMap().layerProperties.get("river-flow:visibility");

  it("drifts along the rivers", async () => {
    stubNode({ eventT: SURGE_T + 60 });
    render(<App />);
    await waitFor(() => expect(visibility()).toBe("visible"));
  });

  it("is off with reduced motion, and the front stops animating", async () => {
    setReducedMotion(true);
    const frames = vi.spyOn(window, "requestAnimationFrame");
    stubNode({ eventT: SURGE_T + 60, state: "playing" });
    render(<App />);
    await waitFor(() => expect(visibility()).toBe("none"));
    // Still marked on the map, as a static reach.
    await waitFor(() => expect(features("wave-head")).toBe(1));
    expect(frames).not.toHaveBeenCalled();
  });
});
