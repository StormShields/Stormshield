import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { setViewport } from "./fakeViewport";
import type { NodeState } from "./nodeState";

function stubNode(state: Partial<NodeState> = {}) {
  const answers: Record<string, unknown> = {
    "/api/state": nepalNodeState({ nodes: [fakeNodeSnapshot("porch")], ...state }),
    "/api/cache-pack": { available: false, manifest: null },
    "/api/shelters": { open: [] },
    "/api/replay": { state: "paused", event_t: 1_787_700_000, rate: 30 },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url in answers ? Response.json(answers[url]) : new Response(null, { status: 404 }),
    ),
  );
}

const tab = (name: string) => screen.getByRole("tab", { name });
const comesBefore = (first: HTMLElement, second: HTMLElement) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("the phone layout", () => {
  it("keeps only the logo, the Flood Risk chip and the connection pill in the top bar", async () => {
    stubNode();
    setViewport(390);
    render(<App />);

    const bar = screen.getByRole("banner");
    expect(within(bar).getByText("Storm Shield")).toBeInTheDocument();
    expect(await within(bar).findByText("Online")).toBeInTheDocument();
    expect(within(bar).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((each) => each.textContent)).toEqual([
      "Map",
      "Readings",
      "Alerts",
      "Plan",
    ]);
    expect(tab("Map")).toHaveAttribute("aria-selected", "true");
  });

  it("shows each tab's content: Readings, Alerts, and the Plan with the profile first", async () => {
    stubNode();
    setViewport(390);
    render(<App />);
    await screen.findByText("Online");

    fireEvent.click(tab("Readings"));
    expect(screen.getByRole("region", { name: "Readings" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Alerts" })).not.toBeInTheDocument();

    fireEvent.click(tab("Alerts"));
    expect(screen.getByRole("region", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Readings" })).not.toBeInTheDocument();

    fireEvent.click(tab("Plan"));
    const profile = screen.getByRole("region", { name: "Household Profile" });
    expect(comesBefore(profile, screen.getByRole("region", { name: "Evacuation Plan" }))).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Set up your household" }));
    expect(screen.getByRole("dialog", { name: "My household" })).toBeInTheDocument();
  });

  it("opens a bottom sheet for a Node selected on the map, and closes it", async () => {
    stubNode();
    setViewport(390);
    render(<App />);
    await waitFor(() => expect(document.querySelector(".node-marker")).not.toBeNull());

    expect(screen.queryByRole("region", { name: /Selected Node/ })).not.toBeInTheDocument();
    fireEvent.click(document.querySelector(".node-marker")!);
    const sheet = screen.getByRole("region", { name: "Selected Node porch" });
    expect(within(sheet).getByText(/Pressure: 1015 hPa/)).toBeInTheDocument();

    fireEvent.click(within(sheet).getByRole("button", { name: "Close Node sheet" }));
    expect(screen.queryByRole("region", { name: /Selected Node/ })).not.toBeInTheDocument();
  });

  it("pins the latest Official Alert on the Map tab", async () => {
    stubNode({
      official_alerts: [
        {
          id: "a1",
          source: "dhm",
          mode: "replay",
          issued: "2026-08-26T09:05:00+05:45",
          headline: "Flood notice for the Bhote Koshi",
          applies_to: [],
          url: "https://example.org",
        },
      ],
    });
    setViewport(390);
    render(<App />);

    expect(await screen.findByRole("status")).toHaveTextContent("Flood notice for the Bhote Koshi");
  });

  it("leaves the desktop layout alone from 900 px up", async () => {
    stubNode();
    setViewport(900);
    render(<App />);
    await screen.findByText("Online");

    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "My household" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Layers" })).toBeInTheDocument();
  });

  it("keeps one Panel open per side on a tablet", async () => {
    stubNode();
    setViewport(1000);
    render(<App />);
    await screen.findByText("Online");

    fireEvent.click(screen.getByRole("button", { name: "Alerts" }));
    fireEvent.click(screen.getByRole("button", { name: "Expand Evacuation Plan" }));
    expect(screen.getByRole("button", { name: "Collapse Evacuation Plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand Alerts" })).toBeInTheDocument();
  });
});
