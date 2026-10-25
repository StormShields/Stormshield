import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { BASEMAP_MANIFEST_PARTS } from "./fakeBasemap";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { lastMap } from "./fakeMaplibre";
import { fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import { setReducedMotion } from "./fakeViewport";
import type { OfficialAlert } from "./officialAlerts";
import { TERRAIN_PITCH, VALLEY_VIEW } from "./terrain";

const SURGE_T = Date.parse("2026-08-26T02:52:00Z") / 1000;
const S0_POSITION: [number, number] = [28.05, 85.27];

const WARNING: CommunityWarning = {
  id: 7,
  t: SURGE_T + 3,
  nodes: ["s0"],
  hazard: "flash_flood",
  reasons: ["water_surge"],
  origin: "s0",
  origin_km: -12.2,
  surge_t: SURGE_T,
};

const NOTICE: OfficialAlert = {
  id: "dhm-notice",
  source: "dhm",
  mode: "replay",
  issued: "2026-08-26T09:05:00+05:45",
  headline: "Authorities learn that a major flood has entered the Bhote Koshi",
  applies_to: [],
  url: "https://example.org/notice",
};

const NEPAL_MANIFEST = {
  built: "2026-10-18T12:00:00+00:00",
  bbox: [27.86, 85.08, 28.46, 85.47],
  ...BASEMAP_MANIFEST_PARTS,
};

let answers: { warnings: CommunityWarning[]; alerts: OfficialAlert[] };

function stubNode() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const known: Record<string, unknown> = {
        "/api/state": fakeNodeState({
          id: "porch",
          community_warnings: answers.warnings,
          official_alerts: answers.alerts,
          nodes: [
            fakeNodeSnapshot("s0", { name: "S0 Lhende", river_km: -12.2, position: S0_POSITION }),
          ],
        }),
        "/api/cache-pack": { available: true, manifest: NEPAL_MANIFEST },
        "/api/cache-pack/files/shelters.json": [],
        "/api/cache-pack/files/flood_prone.geojson": { type: "FeatureCollection", features: [] },
        "/api/cache-pack/files/basemap/places.geojson": { type: "FeatureCollection", features: [] },
        "/api/shelters": { open: [] },
      };
      return url in known ? Response.json(known[url]) : new Response(null, { status: 404 });
    }),
  );
}

function band() {
  return screen.findByRole("alert", { name: "Warning" });
}

function alertsPanel() {
  return within(screen.getByRole("region", { name: "Alerts" }));
}

beforeEach(() => {
  answers = { warnings: [], alerts: [] };
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("the warning band on a desktop", () => {
  it("shows the tag, the sentence and the fixed line with no button, and leaves the map undimmed", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);

    const shown = await band();
    expect(within(shown).getByText("FLASH FLOOD · COMMUNITY WARNING · NOT OFFICIAL")).toBeVisible();
    expect(within(shown).getByText(/S0 Lhende/)).toBeVisible();
    expect(
      within(shown).getByText("Check official sources for any evacuation decision."),
    ).toBeVisible();
    expect(within(shown).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(document.querySelector(".takeover-scrim")).toBeNull();
    expect(document.querySelector<HTMLElement>(".node-map")?.style.opacity).toBe("");
  });

  it("stays until the card in the Alerts Panel is acknowledged, then leaves a chip", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await band();
    expect(screen.queryByRole("button", { name: /WARNING/ })).toBeNull();

    fireEvent.click(
      within(await screen.findByRole("article", { name: "Community Warning" })).getByRole(
        "button",
        { name: "Acknowledge" },
      ),
    );

    expect(screen.queryByRole("alert", { name: "Warning" })).toBeNull();
    expect(alertsPanel().getByText("Acknowledged")).toBeVisible();
    const chip = screen.getByRole("button", { name: /^WARNING/ });
    expect(chip).toHaveClass("community");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows Official first with the count, then Community", async () => {
    answers = { warnings: [WARNING], alerts: [NOTICE] };
    stubNode();
    render(<App />);

    const first = await band();
    expect(within(first).getByText("OFFICIAL · REPLAY")).toBeVisible();
    expect(within(first).getByText("1 of 2")).toBeVisible();

    fireEvent.click(
      within(await screen.findByRole("article", { name: "Official Alert" })).getByRole("button", {
        name: "Acknowledge",
      }),
    );
    const second = await band();
    expect(
      within(second).getByText("FLASH FLOOD · COMMUNITY WARNING · NOT OFFICIAL"),
    ).toBeVisible();
    expect(screen.queryByText("1 of 2")).toBeNull();
  });
});

describe("the camera and the origin Node", () => {
  it("flies flat to the Surging Node, then eases to the valley angle, once", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await band();

    await waitFor(() =>
      expect(lastMap().eased.at(-1)).toEqual({ pitch: TERRAIN_PITCH, duration: 1500 }),
    );
    const flight = lastMap().flights.at(-1);
    expect(flight).toMatchObject({
      center: [S0_POSITION[1], S0_POSITION[0]],
      zoom: VALLEY_VIEW.zoom,
      pitch: 0,
    });
    const flights = lastMap().flights.length;

    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect(lastMap().flights.length).toBe(flights);
  });

  it("rings the origin Node red as the band appears", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await band();
    await waitFor(() => expect(document.querySelectorAll(".origin-ring")).toHaveLength(1));
    expect(document.querySelector(".node-marker .origin-ring")).not.toBeNull();
  });

  it("jumps instead of flying with reduced motion", async () => {
    setReducedMotion(true);
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await band();

    await waitFor(() => expect(lastMap().jumps).toHaveLength(1));
    expect(lastMap().flights).toHaveLength(0);
    expect(lastMap().jumps[0]).toMatchObject({ zoom: VALLEY_VIEW.zoom, pitch: TERRAIN_PITCH });
  });

  it("does not fly again for a warning this device already acknowledged", async () => {
    localStorage.setItem("storm-shield.acknowledged-warnings", JSON.stringify(["community:7"]));
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await screen.findByRole("region", { name: "Alerts" });
    act(() => {});
    expect(lastMap().flights).toHaveLength(0);
    expect(screen.queryByRole("alert", { name: "Warning" })).toBeNull();
  });
});
