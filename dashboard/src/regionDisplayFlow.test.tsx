import { render, screen, within } from "@testing-library/react";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { FAKE_REGION, NEPAL_REGION, fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import type { NodeState } from "./nodeState";

// 14:06 EDT on 28 Sep 2022.
const IAN_AFTERNOON = Date.UTC(2022, 8, 28, 18, 6) / 1000;

const WARNING: CommunityWarning = {
  id: 7,
  t: IAN_AFTERNOON + 3,
  nodes: ["bay"],
  hazard: "flash_flood",
  reasons: ["water_surge"],
  origin: "bay",
  origin_km: -12.2,
  surge_t: IAN_AFTERNOON,
};

function stubNode(state: NodeState, replay?: object) {
  vi.stubGlobal("fetch", async (path: string) => {
    if (path === "/api/state") return Response.json(state);
    if (path === "/api/replay" && replay) return Response.json(replay);
    return new Response(null, { status: 404 });
  });
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("the Event clock tag reads in the Region's time zone with its label", async () => {
  stubNode(fakeNodeState({ region: FAKE_REGION }), {
    v: 1,
    kind: "replay",
    state: "playing",
    event_t: IAN_AFTERNOON,
    rate: 30,
  });
  render(<App />);
  expect(await screen.findByText("28 Sep 2022 · 14:06 EDT · REPLAY ×30")).toBeInTheDocument();
});

test("readings show in the Region's feet, inches per hour and inHg while the wire stays metric", async () => {
  stubNode(
    fakeNodeState({
      region: FAKE_REGION,
      nodes: [
        fakeNodeSnapshot("bay", {
          measurements: {
            water_level: { value: 1.5, unit: "m" },
            rain_rate: { value: 10, unit: "mm/h" },
            air_pressure: { value: 1013.25, unit: "hPa" },
          },
        }),
      ],
    }),
  );
  render(<App />);
  expect(await screen.findByText(/Water level: 4\.9 ft/)).toBeInTheDocument();
  expect(screen.getByText(/Rain rate: 0\.39 in\/h/)).toBeInTheDocument();
  expect(screen.getByText(/Pressure: 29\.92 inHg/)).toBeInTheDocument();
});

test("a Nepal Region keeps metres of water in centimetres", async () => {
  stubNode(
    fakeNodeState({
      region: NEPAL_REGION,
      nodes: [
        fakeNodeSnapshot("bay", { measurements: { water_level: { value: 1.5, unit: "m" } } }),
      ],
    }),
  );
  render(<App />);
  expect(await screen.findByText(/Water level: 150 cm/)).toBeInTheDocument();
});

test("a Community Warning gives its distance in miles for a Fort Myers Region", async () => {
  stubNode(
    fakeNodeState({
      region: FAKE_REGION,
      id: "porch",
      role: "sensor",
      community_warnings: [WARNING],
      nodes: [
        fakeNodeSnapshot("bay", { name: "Bay", river_km: -12.2 }),
        fakeNodeSnapshot("porch", { river_km: 0 }),
      ],
    }),
  );
  render(<App />);
  const card = await screen.findByRole("article", { name: "Community Warning" });
  expect(
    within(card).getByText("Water is surging at Bay, 7.6 mi upstream of this Node"),
  ).toBeVisible();
});

test("a coast Sensor that sends no water level reads as dry", async () => {
  stubNode(
    fakeNodeState({
      region: FAKE_REGION,
      nodes: [
        fakeNodeSnapshot("inland", { measurements: { air_pressure: { value: 990, unit: "hPa" } } }),
      ],
    }),
  );
  render(<App />);
  const card = await screen.findByRole("region", { name: "Node inland" });
  expect(within(card).getByText("Water level: dry")).toBeInTheDocument();
});

test("a real coast Sensor with no water level is not called dry, since it may have no gauge", async () => {
  stubNode(
    fakeNodeState({
      region: FAKE_REGION,
      nodes: [
        fakeNodeSnapshot("pi", {
          simulated: false,
          measurements: { air_pressure: { value: 990, unit: "hPa" } },
        }),
      ],
    }),
  );
  render(<App />);
  const card = await screen.findByRole("region", { name: /Node pi/ });
  expect(within(card).queryByText(/dry/)).not.toBeInTheDocument();
});

test("a river Sensor off the river does not claim to be dry", async () => {
  stubNode(
    fakeNodeState({
      region: NEPAL_REGION,
      nodes: [
        fakeNodeSnapshot("porch", { measurements: { air_pressure: { value: 990, unit: "hPa" } } }),
      ],
    }),
  );
  render(<App />);
  const card = await screen.findByRole("region", { name: "Node porch" });
  expect(within(card).queryByText(/dry/)).not.toBeInTheDocument();
});
