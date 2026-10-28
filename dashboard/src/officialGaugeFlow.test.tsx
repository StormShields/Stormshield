import { render, screen } from "@testing-library/react";

import { App } from "./App";
import { FORT_MYERS_REGION, fakeNodeState } from "./fakeNodeState";
import type { OfficialGauge } from "./nodeState";

const GAUGE: OfficialGauge = {
  agency: "NOAA",
  station: "8725520",
  label: "Fort Myers (NOAA tide gauge)",
  pos: [26.64778, -81.87111],
  level_m: 1,
  observed: Date.UTC(2022, 8, 28, 22, 30) / 1000,
  mode: "live",
};

function stubNode(gauges: OfficialGauge[]) {
  const state = fakeNodeState({ region: FORT_MYERS_REGION, official_gauges: gauges });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/state"
        ? Response.json(state)
        : url === "/api/shelters"
          ? Response.json({ open: [] })
          : new Response(null, { status: 404 }),
    ),
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("an Official Gauge is marked with its agency, station, level and time, apart from Nodes", async () => {
  stubNode([GAUGE]);
  render(<App />);

  expect(await screen.findByText("NOAA 8725520 · 3.3 ft · 18:30 EDT")).toBeVisible();
  expect(document.querySelectorAll(".official-gauge-marker")).toHaveLength(1);
  expect(document.querySelectorAll(".node-marker")).toHaveLength(0);
});

test("a gauge the Hub has not sent a level for says so", async () => {
  stubNode([{ ...GAUGE, level_m: null, observed: null, mode: null }]);
  render(<App />);

  expect(await screen.findByText("NOAA 8725520 · no level yet")).toBeVisible();
});
