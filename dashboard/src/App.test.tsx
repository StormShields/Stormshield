import { fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import type { FloodRisk } from "./nodeState";

const CALM: FloodRisk = {
  level: null,
  reasons: [],
  storm_signal: { on: false, nodes: 0, pressure_hpa: null },
  nodes: { porch: null, garage: null },
  surged: [],
};

const HIGH: FloodRisk = {
  level: "high",
  reasons: [
    { code: "water_high", nodes: 1, value: 90 },
    { code: "rain_heavy", nodes: 2, value: 30 },
    { code: "pressure_falling", nodes: 2, value: 995 },
  ],
  storm_signal: { on: true, nodes: 2, pressure_hpa: 995 },
  nodes: { porch: "high", garage: null },
  surged: [],
};

const LOW_FROM_STORM_SIGNAL: FloodRisk = {
  level: "low",
  reasons: [{ code: "pressure_falling", nodes: 3, value: 1002 }],
  storm_signal: { on: true, nodes: 3, pressure_hpa: 1002 },
  nodes: { porch: null, garage: null },
  surged: [],
};

const SURGE: FloodRisk = {
  level: "high",
  reasons: [
    { code: "water_surge", nodes: 1, value: 320, seconds: 8 },
    { code: "water_high", nodes: 1, value: 340 },
    { code: "water_rising", nodes: 1, value: 320 },
  ],
  storm_signal: { on: false, nodes: 0, pressure_hpa: null },
  nodes: { porch: "high", garage: null },
  surged: ["porch"],
};

const GARAGE_AGE_SECONDS = 40;

function stubFloodRisk(floodRisk: FloodRisk) {
  const state = nepalNodeState({
    flood_risk: floodRisk,
    nodes: [
      fakeNodeSnapshot("garage", {
        position: [29.654, -82.322],
        age_s: GARAGE_AGE_SECONDS,
        stale: true,
        measurements: { air_pressure: { value: 1002, unit: "hPa" } },
      }),
      fakeNodeSnapshot("porch"),
    ],
  });
  vi.stubGlobal("fetch", async (path: string) => {
    if (path === "/api/state") return Response.json(state);
    return new Response(null, { status: 404 });
  });
}

beforeEach(() => {
  stubFloodRisk(CALM);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("says Connecting… until the Node answers, not an error", async () => {
  vi.stubGlobal("fetch", () => new Promise(() => {}));
  render(<App />);
  expect(screen.getByText("Connecting…")).toBeInTheDocument();
  expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument();
});

test("shows the Node's name and role and the placeholder areas", async () => {
  render(<App />);
  expect(await screen.findByText("porch · Hub")).toBeInTheDocument();
  for (const area of ["Map", "Readings", "Alerts", "Evacuation Plan"]) {
    expect(screen.getByRole("region", { name: area })).toBeInTheDocument();
  }
});

test("lists readings labeled as simulated", async () => {
  render(<App />);
  expect(await screen.findByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
  expect(screen.getAllByText("SIMULATED").length).toBeGreaterThanOrEqual(2);
});

test("lists readings from other Nodes under each Node's name", async () => {
  render(<App />);
  const garage = await screen.findByRole("region", { name: "Node garage" });
  expect(within(garage).getByText(/Pressure: 1002 hPa/)).toBeInTheDocument();
  expect(
    within(screen.getByRole("region", { name: "Node porch" })).getByText(/Pressure: 1015 hPa/),
  ).toBeInTheDocument();
});

test("a silent Node is greyed with STALE and its age, as the Node decided", async () => {
  render(<App />);
  const garage = await screen.findByRole("region", { name: "Node garage" });
  expect(within(garage).getByText("STALE · 40 s")).toBeInTheDocument();
  const porch = screen.getByRole("region", { name: "Node porch" });
  expect(within(porch).queryByText(/STALE/)).not.toBeInTheDocument();
});

test("selecting a card marks it as the selected Node", async () => {
  render(<App />);
  const garage = await screen.findByRole("region", { name: "Node garage" });
  fireEvent.click(garage);
  expect(garage).toHaveAttribute("aria-current", "true");
  expect(screen.getByRole("region", { name: "Node porch" })).toHaveAttribute(
    "aria-current",
    "false",
  );
});

test("selecting the selected card again clears the selection", async () => {
  render(<App />);
  const garage = await screen.findByRole("region", { name: "Node garage" });
  fireEvent.click(garage);
  fireEvent.click(garage);
  expect(garage).toHaveAttribute("aria-current", "false");
});

test("on a calm day no Flood Risk is shown", async () => {
  render(<App />);
  await screen.findByText("porch · Hub");
  expect(screen.queryByRole("region", { name: "Flood Risk" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Flood Risk ·/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Low pressure/)).not.toBeInTheDocument();
});

test("High Flood Risk shows its level in the top bar and its reasons on the card", async () => {
  stubFloodRisk(HIGH);
  render(<App />);
  const card = await screen.findByRole("region", { name: "Flood Risk" });
  expect(within(card).getByText("Flood Risk · High")).toBeInTheDocument();
  expect(within(card).getByText("water level 90 cm at 1 Node")).toBeInTheDocument();
  expect(within(card).getByText("heavy rain: 30 mm/h at 2 Nodes")).toBeInTheDocument();
  expect(screen.getAllByText("Flood Risk · High")).toHaveLength(2);
});

test("a Surge says how far the water rose and how long it took, without repeating that it is rising", async () => {
  stubFloodRisk(SURGE);
  render(<App />);
  const card = await screen.findByRole("region", { name: "Flood Risk" });
  expect(within(card).getByText("water rose 320 cm in 8 s")).toBeInTheDocument();
  expect(within(card).getByText("water level 340 cm at 1 Node")).toBeInTheDocument();
  expect(within(card).queryByText(/rising/)).not.toBeInTheDocument();
});

test("a Surge seen within one reading interval says the water rose at once", async () => {
  stubFloodRisk({
    ...SURGE,
    reasons: [{ code: "water_surge", nodes: 1, value: 150, seconds: 0 }],
  });
  render(<App />);
  const card = await screen.findByRole("region", { name: "Flood Risk" });
  expect(within(card).getByText("water rose 150 cm at once")).toBeInTheDocument();
});

test("the Storm Signal sits in the top bar and the card leaves it out when other reasons exist", async () => {
  stubFloodRisk(HIGH);
  render(<App />);
  const topBar = await screen.findByRole("banner");
  expect(await within(topBar).findByText("Low pressure: 995 hPa at 2 Nodes")).toBeInTheDocument();
  const card = screen.getByRole("region", { name: "Flood Risk" });
  expect(within(card).queryByText(/low pressure/)).not.toBeInTheDocument();
});

test("the card repeats the Storm Signal when it is the only reason for Low", async () => {
  stubFloodRisk(LOW_FROM_STORM_SIGNAL);
  render(<App />);
  const card = await screen.findByRole("region", { name: "Flood Risk" });
  expect(within(card).getByText("Flood Risk · Low")).toBeInTheDocument();
  expect(within(card).getByText("low pressure: 1002 hPa at 3 Nodes")).toBeInTheDocument();
});

test("a Node at High shows its own level word and a Node with no level shows none", async () => {
  stubFloodRisk(HIGH);
  render(<App />);
  const porch = await screen.findByRole("region", { name: "Node porch" });
  expect(await within(porch).findByText("HIGH")).toBeInTheDocument();
  const garage = screen.getByRole("region", { name: "Node garage" });
  expect(within(garage).queryByText("HIGH")).not.toBeInTheDocument();
});
