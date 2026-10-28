import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { expandPanel } from "./expandPanel";
import { fakeNodeState } from "./fakeNodeState";

const SHELTERS = [
  { id: "test-gym", name: "Test Gym", pos: [29.66, -82.32] },
  { id: "far-hall", name: "Far Hall", pos: [29.7, -82.32] },
].map((shelter) => ({ ...shelter, special_needs: false, pet_friendly: false }));

let openIds: string[];
let postedBodies: unknown[];
let refusal: string | null;
let live: boolean;
// Polls wait on this before answering, so a test can leave one in flight.
let heldPolls: Promise<void>;

function stubNode(role: "hub" | "sensor") {
  const answers: Record<string, unknown> = {
    "/api/state": fakeNodeState({ role, live }),
    "/api/replay": { state: "stopped" },
    "/api/replay/events": { events: [{ id: "bhote-koshi", label: "Bhote Koshi 2026" }] },
    "/api/cache-pack": { available: true, manifest: null },
    "/api/cache-pack/files/shelters.json": SHELTERS,
    "/api/cache-pack/files/flood_prone.geojson": { type: "FeatureCollection", features: [] },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/shelters/open") {
        if (refusal) return Response.json({ detail: refusal }, { status: 422 });
        const body = JSON.parse(init?.body as string);
        postedBodies.push(body);
        openIds = body.open
          ? [...openIds, body.id]
          : openIds.filter((openId) => openId !== body.id);
        return Response.json({ open: openIds });
      }
      if (url === "/api/shelters") {
        const listAtRequest = openIds;
        await heldPolls;
        return Response.json({ open: listAtRequest });
      }
      return url in answers ? Response.json(answers[url]) : new Response(null, { status: 404 });
    }),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
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
  openIds = ["test-gym", "far-hall"];
  postedBodies = [];
  refusal = null;
  live = false;
  heldPolls = Promise.resolve();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("a Sensor Node has no Hub button", async () => {
  stubNode("sensor");
  render(<App />);
  expandPanel("Evacuation Plan");

  expect(await screen.findByText(/porch · Sensor Node/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "Hub" })).toBeNull();
});

test("the Hub Panel lists every Shelter and closing one posts the right body", async () => {
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Shelters" }));
  expect(await within(panel).findByText("Far Hall")).toBeVisible();
  expect(within(panel).getAllByText("Open")).toHaveLength(2);

  fireEvent.click(within(panel).getByRole("button", { name: "Close Far Hall" }));

  expect(await within(panel).findByRole("button", { name: "Open Far Hall" })).toBeVisible();
  expect(postedBodies).toEqual([{ id: "far-hall", open: false }]);
  expect(within(panel).getByText("Closed")).toBeVisible();
});

test("a closed Shelter can be opened again", async () => {
  openIds = ["test-gym"];
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Shelters" }));
  fireEvent.click(await within(panel).findByRole("button", { name: "Open Far Hall" }));

  expect(await within(panel).findByRole("button", { name: "Close Far Hall" })).toBeVisible();
  expect(postedBodies).toEqual([{ id: "far-hall", open: true }]);
  expect(within(panel).queryByText("Closed")).toBeNull();
});

test("a poll that began before a change does not bring back the old list", async () => {
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");
  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Shelters" }));
  expect(await within(panel).findByText("Far Hall")).toBeVisible();

  let releasePolls = () => {};
  heldPolls = new Promise((resolve) => (releasePolls = resolve));
  await act(() => vi.advanceTimersByTimeAsync(5000));
  fireEvent.click(within(panel).getByRole("button", { name: "Close Far Hall" }));
  expect(await within(panel).findByText("Closed")).toBeVisible();

  await act(async () => releasePolls());

  expect(within(panel).getByText("Closed")).toBeVisible();
});

test("opening the Hub Panel closes the household panel", async () => {
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");

  fireEvent.click(screen.getByRole("button", { name: "My household" }));
  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));

  expect(screen.queryByRole("dialog", { name: "My household" })).toBeNull();
  expect(screen.getByRole("dialog", { name: "Hub Panel" })).toBeVisible();
});

test("a closed nearest Shelter changes the plan on the next poll", async () => {
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");
  expect(await screen.findByText(/Nearest open Shelter: Test Gym/)).toBeVisible();

  openIds = ["far-hall"];
  await act(() => vi.advanceTimersByTimeAsync(5000));

  expect(await screen.findByText(/Nearest open Shelter: Far Hall/)).toBeVisible();
});

test("a refused change is shown in the panel and leaves the list as it was", async () => {
  stubNode("hub");
  refusal = "unknown Shelter 'far-hall'";
  render(<App />);
  expandPanel("Evacuation Plan");

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Shelters" }));
  fireEvent.click(await within(panel).findByRole("button", { name: "Close Far Hall" }));

  expect(await within(panel).findByRole("alert")).toHaveTextContent(
    "Could not close Far Hall: unknown Shelter 'far-hall'",
  );
  expect(within(panel).getAllByText("Open")).toHaveLength(2);
});

test("a Live Hub's Replay tab explains why no Replay can play, and the controls return after", async () => {
  live = true;
  stubNode("hub");
  render(<App />);
  expandPanel("Evacuation Plan");
  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Replay" }));

  expect(
    await within(panel).findByText("Live Sensors are reporting, so no Replay can play."),
  ).toBeVisible();
  expect(within(panel).queryByLabelText("Event")).toBeNull();
  expect(within(panel).queryByRole("button", { name: "Start" })).toBeNull();
  expect(within(panel).queryByText("REPLAY")).toBeNull();

  live = false;
  stubNode("hub");
  await act(() => vi.advanceTimersByTimeAsync(5000));

  expect(await within(panel).findByRole("button", { name: "Start" })).toBeVisible();
  expect(within(panel).getByLabelText("Event")).toBeVisible();
  expect(within(panel).getByText("REPLAY")).toBeVisible();
  expect(within(panel).queryByText(/no Replay can play/)).toBeNull();
});
