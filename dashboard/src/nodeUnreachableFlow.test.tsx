import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import type { OfficialAlert } from "./officialAlerts";

const NOTICE: OfficialAlert = {
  id: "dhm-notice",
  source: "dhm",
  mode: "replay",
  issued: "2026-08-26T09:05:00+05:45",
  headline: "Authorities learn that a major flood has entered the Bhote Koshi",
  applies_to: [],
  url: "https://example.org/notice",
};

const SHELTERS = [{ id: "test-gym", name: "Test Gym", pos: [29.66, -82.32] }].map((shelter) => ({
  ...shelter,
  special_needs: false,
  pet_friendly: false,
}));

// How the fake Node answers: well, with an HTTP error, not at all, or by hanging until the request
// is given up on.
let nodeAnswer: "ok" | "error" | "down" | "hangs";
// Let the open-Shelter list or the Event clock fail while the rest of the Node answers.
let sheltersDown: boolean;
let eventClockDown: boolean;
let requests: string[];

function hangUntilGivenUp(signal?: AbortSignal | null) {
  return new Promise<Response>((_, reject) => {
    signal?.addEventListener("abort", () => reject(new Error("request timed out")));
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(
    "storm-shield.household-profile",
    JSON.stringify({
      version: 1,
      profile: {
        home: { lat: 29.65, lon: -82.32 },
        housing: "site-built",
        needsSpecialNeedsShelter: false,
        needsPetFriendlyShelter: false,
      },
    }),
  );
  nodeAnswer = "ok";
  sheltersDown = false;
  eventClockDown = false;
  requests = [];
  vi.useFakeTimers({ shouldAdvanceTime: true });
  // The real timeout runs on a clock fake timers cannot move; this one runs on the fake clock.
  vi.spyOn(AbortSignal, "timeout").mockImplementation((ms) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), ms);
    return controller.signal;
  });
  vi.stubGlobal("fetch", async (path: string, init?: RequestInit) => {
    requests.push(path);
    if (path.startsWith("/api/cache-pack")) {
      if (path === "/api/cache-pack") return Response.json({ available: true, manifest: null });
      if (path.endsWith("shelters.json")) return Response.json(SHELTERS);
      if (path.endsWith("flood_prone.geojson"))
        return Response.json({ type: "FeatureCollection", features: [] });
    }
    if (nodeAnswer === "down") throw new TypeError("Failed to fetch");
    if (nodeAnswer === "hangs") return hangUntilGivenUp(init?.signal);
    if (path === "/api/state") {
      if (nodeAnswer === "error") return new Response(null, { status: 503 });
      return Response.json(
        nepalNodeState({
          role: "hub",
          status: "online",
          flood_risk: {
            level: "elevated",
            reasons: [{ code: "water_high", nodes: 1, value: 40 }],
            storm_signal: { on: false, nodes: 0, pressure_hpa: null },
            nodes: {},
            surged: [],
          },
          nodes: [fakeNodeSnapshot("porch")],
          official_alerts: [NOTICE],
        }),
      );
    }
    if (path === "/api/replay") {
      if (eventClockDown) throw new TypeError("Failed to fetch");
      return Response.json({ state: "playing", event_t: 1787715660, rate: 30 });
    }
    if (path === "/api/shelters") {
      if (sheltersDown) throw new TypeError("Failed to fetch");
      return Response.json({ open: ["test-gym"] });
    }
    return new Response(null, { status: 404 });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function seconds(count: number) {
  await act(() => vi.advanceTimersByTimeAsync(count * 1000));
}

function banner() {
  return screen.queryByText(/Node unreachable/);
}

async function showLiveData() {
  render(<App />);
  expect(await screen.findByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
  await screen.findByText(/NPT · REPLAY/);
  await screen.findByText(/Nearest open Shelter: Test Gym/);
}

function requestsTo(path: string) {
  return requests.filter((request) => request === path).length;
}

test.each(["down", "error"] as const)(
  "a Node that is %s shows the warning after 5 s with no good answer, not before",
  async (answer) => {
    await showLiveData();
    nodeAnswer = answer;
    await seconds(4);
    expect(banner()).not.toBeInTheDocument();
    expect(screen.getByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
    await seconds(1);
    expect(banner()).toBeInTheDocument();
  },
);

test("a Node that hangs is given up on and shows the warning after 5 s too", async () => {
  await showLiveData();
  nodeAnswer = "hangs";
  await seconds(4);
  expect(banner()).not.toBeInTheDocument();
  await seconds(1);
  expect(banner()).toBeInTheDocument();
});

test("a page whose Node never answers says Connecting…, then Node unreachable after 5 s", async () => {
  nodeAnswer = "down";
  render(<App />);
  expect(screen.getByText("Connecting…")).toBeInTheDocument();
  await seconds(4);
  expect(screen.getByText("Connecting…")).toBeInTheDocument();
  await seconds(1);
  expect(banner()).toBeInTheDocument();
  expect(screen.queryByText("Connecting…")).not.toBeInTheDocument();
});

test("a page whose Node hangs from the start shows the warning after 5 s too", async () => {
  nodeAnswer = "hangs";
  render(<App />);
  await seconds(4);
  expect(screen.getByText("Connecting…")).toBeInTheDocument();
  await seconds(1);
  expect(banner()).toBeInTheDocument();
});

test("failures broken by a good answer never add up to the warning", async () => {
  await showLiveData();
  for (let round = 0; round < 3; round += 1) {
    nodeAnswer = "down";
    await seconds(4);
    nodeAnswer = "ok";
    await seconds(1);
  }
  expect(banner()).not.toBeInTheDocument();
});

test("while unreachable, everything live goes and what helps the resident plan stays", async () => {
  await showLiveData();
  nodeAnswer = "down";
  await seconds(5);

  expect(screen.queryByText(/Pressure: 1015 hPa/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Elevated/)).not.toBeInTheDocument();
  expect(screen.queryByText("Online")).not.toBeInTheDocument();
  expect(screen.queryByText(/NPT · REPLAY/)).not.toBeInTheDocument();

  expect(document.querySelector(".node-map")).toBeInTheDocument();
  expect(screen.getByText("Household profile saved")).toBeInTheDocument();
  expect(screen.getByText("porch · Hub")).toBeInTheDocument();
  expect(
    within(screen.getByRole("region", { name: "Alerts" })).getByText(NOTICE.headline),
  ).toBeInTheDocument();
  expect(screen.getByText(/Nearest open Shelter: Test Gym/)).toBeInTheDocument();
});

test("Event clock polling stops while unreachable and resume after", async () => {
  await showLiveData();
  nodeAnswer = "down";
  await seconds(5);
  await seconds(1);
  const clockRequests = requestsTo("/api/replay");
  await seconds(10);
  expect(requestsTo("/api/replay")).toBe(clockRequests);

  nodeAnswer = "ok";
  await seconds(1);
  expect(await screen.findByText(/NPT · REPLAY/)).toBeInTheDocument();
});

test("the plan says how long ago Shelter status was last confirmed, and the age grows", async () => {
  await showLiveData();
  expect(screen.queryByText(/Shelter status last confirmed/)).not.toBeInTheDocument();
  nodeAnswer = "down";
  await seconds(5);
  const line = () => screen.getByText(/Shelter status last confirmed/);
  expect(line()).toHaveTextContent(/confirmed [56] s ago; it may have changed since/);
  await seconds(10);
  expect(line()).toHaveTextContent(/confirmed 1[56] s ago/);
});

test("on an unreachable Hub the Replay controls wait instead of offering Start", async () => {
  await showLiveData();
  fireEvent.click(screen.getByRole("button", { name: "Hub" }));
  fireEvent.click(screen.getByRole("tab", { name: "Replay" }));
  const replay = () => within(screen.getByRole("region", { name: "Replay controls" }));
  expect(replay().getByRole("button", { name: "Pause" })).toBeInTheDocument();

  nodeAnswer = "down";
  await seconds(5);
  expect(replay().getByText("Waiting for the Hub to answer")).toBeInTheDocument();
  expect(replay().queryByRole("button")).not.toBeInTheDocument();

  nodeAnswer = "ok";
  await seconds(1);
  expect(await replay().findByRole("button", { name: "Pause" })).toBeInTheDocument();
});

test("back from unreachable, the Replay controls wait for the Event clock, never offering Start", async () => {
  await showLiveData();
  fireEvent.click(screen.getByRole("button", { name: "Hub" }));
  fireEvent.click(screen.getByRole("tab", { name: "Replay" }));
  nodeAnswer = "down";
  await seconds(5);
  eventClockDown = true;
  nodeAnswer = "ok";
  await seconds(3);
  expect(screen.getByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
  const replay = within(screen.getByRole("region", { name: "Replay controls" }));
  expect(replay.getByText("Waiting for the Hub to answer")).toBeInTheDocument();
  expect(replay.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
});

test("the next good answer clears the warning and the Shelter line and restores the data", async () => {
  await showLiveData();
  nodeAnswer = "down";
  await seconds(5);
  expect(banner()).toBeInTheDocument();
  nodeAnswer = "ok";
  await seconds(1);
  expect(banner()).not.toBeInTheDocument();
  expect(screen.queryByText(/Shelter status last confirmed/)).not.toBeInTheDocument();
  expect(screen.getByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
  expect(screen.getByText("Online")).toBeInTheDocument();
});

test("a failed poll of the open-Shelter list keeps the last list", async () => {
  await showLiveData();
  sheltersDown = true;
  await seconds(10);
  expect(banner()).not.toBeInTheDocument();
  expect(screen.getByText(/Nearest open Shelter: Test Gym/)).toBeInTheDocument();
});
