import { fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeState } from "./fakeNodeState";

// 08:30 NPT on 26 Aug 2026; each phase is that many minutes on.
const REPLAY_START = 1787712300;
const PHASES = [
  { id: "calm", label: "Calm", event_t: REPLAY_START },
  { id: "collapse", label: "Collapse above the Lhende Khola", event_t: REPLAY_START + 7 * 60 },
];
const INTERNET_CUE = REPLAY_START + 50 * 60;

const EVENTS = {
  events: [
    {
      id: "bhote-koshi-2026",
      label: "Bhote Koshi flood",
      real: true,
      reconstructed_stations: [],
    },
    { id: "made-up-flood", label: "A made-up flood", real: false, reconstructed_stations: [] },
  ],
};
const IAN = {
  id: "ian-2022",
  label: "Hurricane Ian storm surge",
  real: true,
  reconstructed_stations: ["Fort Myers Beach Pier", "Estero Bay at Coconut Point Marina"],
};
const MADE_UP_PHASES = [{ id: "only", label: "The only phase", event_t: REPLAY_START }];

let replay: object;
let events: object | null;
let sandbox: { label: "SIMULATED" } | null;
let posted: { path: string; body: unknown }[];
let fetched: string[];

beforeEach(() => {
  replay = { v: 1, kind: "replay", state: "stopped", event_t: 0, rate: 1 };
  events = null;
  sandbox = null;
  posted = [];
  fetched = [];
  vi.stubGlobal("fetch", async (path: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ path, body: init.body ? JSON.parse(init.body as string) : undefined });
      return Response.json(replay);
    }
    fetched.push(path);
    if (path === "/api/replay") return Response.json(replay);
    if (path === "/api/replay/events") {
      return events ? Response.json(events) : new Response(null, { status: 404 });
    }
    if (path === "/api/replay/phases") {
      return Response.json({ phases: PHASES, internet_cue_event_t: INTERNET_CUE });
    }
    if (path === "/api/replay/phases?event=made-up-flood") {
      return Response.json({ phases: MADE_UP_PHASES, internet_cue_event_t: INTERNET_CUE });
    }
    if (path === "/api/replay/phases?event=bhote-koshi-2026") {
      return Response.json({ phases: PHASES, internet_cue_event_t: INTERNET_CUE });
    }
    if (path === "/api/sandbox/nodes") return Response.json({ radio_range_m: 40000, nodes: [] });
    if (path === "/api/state") {
      return Response.json(fakeNodeState({ id: "hub", name: "hub", sandbox }));
    }
    return new Response(null, { status: 404 });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function openHubPanel() {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  fireEvent.click(screen.getByRole("tab", { name: "Replay" }));
  return screen.getByRole("dialog", { name: "Hub Panel" });
}

test("Start posts to the Hub, and Reset is always there", async () => {
  const panel = await openHubPanel();
  fireEvent.click(within(panel).getByRole("button", { name: "Start" }));
  fireEvent.click(within(panel).getByRole("button", { name: "Reset" }));
  expect(posted).toEqual([
    { path: "/api/replay/start", body: undefined },
    { path: "/api/replay/reset", body: undefined },
  ]);
});

test("a playing replay offers Pause and highlights the current phase", async () => {
  replay = { v: 1, kind: "replay", state: "playing", event_t: REPLAY_START + 8 * 60, rate: 30 };
  const panel = await openHubPanel();
  fireEvent.click(await within(panel).findByRole("button", { name: "Pause" }));
  expect(posted[0].path).toBe("/api/replay/pause");
  expect(
    await within(panel).findByRole("button", { name: "Collapse above the Lhende Khola" }),
  ).toHaveAttribute("aria-current", "step");
  expect(within(panel).getByRole("button", { name: "Calm" })).not.toHaveAttribute("aria-current");
});

test("a paused replay offers Resume, and a phase button jumps to it", async () => {
  replay = { v: 1, kind: "replay", state: "paused", event_t: REPLAY_START, rate: 30 };
  const panel = await openHubPanel();
  fireEvent.click(await within(panel).findByRole("button", { name: "Resume" }));
  fireEvent.click(await within(panel).findByRole("button", { name: /Collapse/ }));
  expect(posted).toEqual([
    { path: "/api/replay/resume", body: undefined },
    { path: "/api/replay/jump", body: { phase: "collapse" } },
  ]);
});

test("a speed picked before Start is sent ahead of Start", async () => {
  const panel = await openHubPanel();
  expect(within(panel).getByRole("button", { name: "×30" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(within(panel).getByRole("button", { name: "×5" }));
  expect(within(panel).getByRole("button", { name: "×5" })).toHaveAttribute("aria-pressed", "true");
  expect(posted).toEqual([]);
  fireEvent.click(within(panel).getByRole("button", { name: "Start" }));
  await vi.waitFor(() =>
    expect(posted).toEqual([
      { path: "/api/replay/rate", body: { rate: 5 } },
      { path: "/api/replay/start", body: undefined },
    ]),
  );
});

test("a running replay shows its rate and changing it posts to the Hub", async () => {
  replay = { v: 1, kind: "replay", state: "playing", event_t: REPLAY_START, rate: 10 };
  const panel = await openHubPanel();
  expect(await within(panel).findByRole("button", { name: "×10" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(within(panel).getByRole("button", { name: "×5" }));
  expect(posted).toEqual([{ path: "/api/replay/rate", body: { rate: 5 } }]);
});

test("the Hub Panel says to cut the internet once the Event clock reaches the cue", async () => {
  replay = { v: 1, kind: "replay", state: "playing", event_t: INTERNET_CUE - 60, rate: 30 };
  const panel = await openHubPanel();
  await within(panel).findByRole("button", { name: "Pause" });
  expect(within(panel).queryByText("Cut the internet now")).toBeNull();

  replay = { v: 1, kind: "replay", state: "playing", event_t: INTERNET_CUE, rate: 30 };
  expect(
    await within(panel).findByText("Cut the internet now", {}, { timeout: 3000 }),
  ).toBeVisible();
});

test("Resume at the end of the replay shows why the Hub refused it", async () => {
  replay = { v: 1, kind: "replay", state: "paused", event_t: REPLAY_START + 120 * 60, rate: 30 };
  const panel = await openHubPanel();
  const resume = await within(panel).findByRole("button", { name: "Resume" });
  vi.stubGlobal("fetch", async () =>
    Response.json({ detail: "the replay has ended; Reset or jump to a phase" }, { status: 409 }),
  );
  fireEvent.click(resume);
  expect(await within(panel).findByRole("alert")).toHaveTextContent(
    "Could not resume the replay: the replay has ended; Reset or jump to a phase",
  );
});

test("the picker lists the Region's Events, and the picked one is what Start plays", async () => {
  events = EVENTS;
  const panel = await openHubPanel();
  const picker = await within(panel).findByRole("combobox", { name: "Event" });
  expect(
    within(picker)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Bhote Koshi flood", "A made-up flood (made up)"]);
  fireEvent.change(picker, { target: { value: "made-up-flood" } });
  fireEvent.click(await within(panel).findByRole("button", { name: "The only phase" }));
  await vi.waitFor(() =>
    expect(posted).toEqual([
      { path: "/api/replay/jump", body: { phase: "only", event: "made-up-flood" } },
    ]),
  );
  posted.length = 0;
  fireEvent.click(within(panel).getByRole("button", { name: "Start" }));
  await vi.waitFor(() =>
    expect(posted).toEqual([{ path: "/api/replay/start", body: { event: "made-up-flood" } }]),
  );
});

test("a running replay shows its Event, and picking another one starts that", async () => {
  events = EVENTS;
  replay = {
    v: 2,
    kind: "replay",
    event: "made-up-flood",
    state: "playing",
    event_t: REPLAY_START,
    rate: 30,
  };
  const panel = await openHubPanel();
  const picker = await within(panel).findByRole("combobox", { name: "Event" });
  expect(picker).toHaveValue("made-up-flood");
  fireEvent.change(picker, { target: { value: "bhote-koshi-2026" } });
  await vi.waitFor(() =>
    expect(posted).toEqual([{ path: "/api/replay/start", body: { event: "bhote-koshi-2026" } }]),
  );
});

test("a running Event is labelled REPLAY beside its clock", async () => {
  events = EVENTS;
  replay = {
    v: 2,
    kind: "replay",
    event: "bhote-koshi-2026",
    state: "playing",
    event_t: REPLAY_START,
    rate: 30,
  };
  const panel = await openHubPanel();
  expect(await within(panel).findByText("REPLAY")).toBeVisible();
  expect(within(panel).getByText(/REPLAY ×30/)).toBeVisible();
});

test("the Sandbox Panel holds the same Replay controls", async () => {
  events = EVENTS;
  sandbox = { label: "SIMULATED" };
  render(<App />);
  const panel = await screen.findByRole("region", { name: "Sandbox" });
  const picker = await within(panel).findByRole("combobox", { name: "Event" });
  fireEvent.change(picker, { target: { value: "made-up-flood" } });
  fireEvent.click(within(panel).getByRole("button", { name: "Start" }));
  await vi.waitFor(() =>
    expect(posted).toEqual([{ path: "/api/replay/start", body: { event: "made-up-flood" } }]),
  );
});

test("the Replay says which stations' water is reconstructed, only for an Event that has some", async () => {
  events = { events: [IAN, ...EVENTS.events] };
  const panel = await openHubPanel();
  const picker = await within(panel).findByRole("combobox", { name: "Event" });
  expect(
    await within(panel).findByRole("status", { name: "Reconstructed water" }),
  ).toHaveTextContent(
    "Reconstructed, not recorded: Fort Myers Beach Pier, Estero Bay at Coconut Point Marina",
  );
  fireEvent.change(picker, { target: { value: "made-up-flood" } });
  await vi.waitFor(() =>
    expect(within(panel).queryByRole("status", { name: "Reconstructed water" })).toBeNull(),
  );
});
