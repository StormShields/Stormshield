import { act, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { setReducedMotion } from "./fakeViewport";
import { STATE_POLL_MS } from "./useNodeState";

let pressure: number;
// Listed in an order that is not the display order, to show the cards do not follow it.
let nodeOrder: string[];

const SNAPSHOTS: Record<string, () => ReturnType<typeof fakeNodeSnapshot>> = {
  porch: () =>
    fakeNodeSnapshot("porch", { measurements: { air_pressure: { value: pressure, unit: "hPa" } } }),
  barn: () => fakeNodeSnapshot("barn"),
  attic: () => fakeNodeSnapshot("attic"),
  zed: () => fakeNodeSnapshot("zed", { registered: false }),
};

beforeEach(() => {
  pressure = 1015;
  nodeOrder = ["zed", "barn", "porch", "attic"];
  vi.stubGlobal("fetch", async (path: string) => {
    if (path === "/api/state") {
      return Response.json(nepalNodeState({ nodes: nodeOrder.map((id) => SNAPSHOTS[id]()) }));
    }
    return new Response(null, { status: 404 });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const cardNames = () =>
  screen.getAllByRole("region", { name: /^Node / }).map((card) => card.getAttribute("aria-label"));

test("cards stay this Node, the Registered Nodes A to Z, then Not counted, whatever order a poll lists them in", async () => {
  render(<App />);
  await screen.findByRole("region", { name: "Node porch" });
  const expected = ["Node porch", "Node attic", "Node barn", "Node zed"];
  expect(cardNames()).toEqual(expected);
  nodeOrder = ["attic", "zed", "porch", "barn"];
  await act(() => vi.advanceTimersByTimeAsync(2 * STATE_POLL_MS));
  expect(cardNames()).toEqual(expected);
});

test("a falling reading gets a down arrow and its slot flashes", async () => {
  render(<App />);
  const porch = await screen.findByRole("region", { name: "Node porch" });
  expect(await within(porch).findByRole("img", { name: "steady" })).toBeInTheDocument();
  expect(porch.querySelector(".tick")).toBeNull();
  pressure = 1000;
  await act(() => vi.advanceTimersByTimeAsync(STATE_POLL_MS));
  expect(within(porch).getByRole("img", { name: "falling" })).toBeInTheDocument();
  expect(porch.querySelector(".slot-value.tick")).toHaveTextContent("Pressure: 1000 hPa");
});

test("with reduced motion a change is an instant swap: no flash or fade classes", async () => {
  setReducedMotion(true);
  render(<App />);
  const porch = await screen.findByRole("region", { name: "Node porch" });
  pressure = 1000;
  await act(() => vi.advanceTimersByTimeAsync(STATE_POLL_MS));
  expect(within(porch).getByText("Pressure: 1000 hPa")).toBeInTheDocument();
  expect(document.querySelector(".tick, .enters, .fades-in, .card-flash")).toBeNull();
});
