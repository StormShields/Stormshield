import { render, screen } from "@testing-library/react";

import { App } from "./App";
import { nepalNodeState } from "./fakeNodeState";

// 08:41 NPT on 26 Aug 2026: 08:30 is 1787712300 and the Event clock is 11 minutes on.
const EIGHT_FORTY_ONE = 1787712300 + 11 * 60;

let replay: object;

beforeEach(() => {
  replay = { v: 1, kind: "replay", state: "stopped", event_t: 0, rate: 1 };
  vi.stubGlobal("fetch", async (path: string) => {
    if (path === "/api/replay") return Response.json(replay);
    if (path === "/api/state") return Response.json(nepalNodeState({ role: "sensor" }));
    return new Response(null, { status: 404 });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("the header shows the Event clock in Nepal time with the REPLAY tag", async () => {
  replay = { v: 1, kind: "replay", state: "playing", event_t: EIGHT_FORTY_ONE, rate: 30 };
  render(<App />);
  expect(await screen.findByText("26 Aug 2026 · 08:41 NPT · REPLAY ×30")).toBeInTheDocument();
});

test("the header shows no Event clock while no replay is running", async () => {
  render(<App />);
  await screen.findByText("Online");
  expect(screen.queryByText(/REPLAY/)).not.toBeInTheDocument();
});
