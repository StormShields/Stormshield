import { render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { expandPanel } from "./expandPanel";
import { nepalNodeState } from "./fakeNodeState";
import type { OfficialAlert } from "./officialAlerts";

const PROFILE_KEY = "storm-shield.household-profile";
const HOME = { lat: 29.65, lon: -82.32 };

const NOTICE: OfficialAlert = {
  id: "dhm-notice",
  source: "dhm",
  mode: "replay",
  issued: "2026-08-26T09:05:00+05:45",
  headline: "Authorities learn that a major flood has entered the Bhote Koshi",
  applies_to: [],
  url: "https://example.org/notice",
};
const RIVERBANK_SMS: OfficialAlert = {
  ...NOTICE,
  id: "dhm-sms",
  issued: "2026-08-26T09:15:00+05:45",
  headline:
    "SMS to riverbank residents of Rasuwa, Nuwakot, Dhading and Chitwan: remain on high alert",
  applies_to: ["flood_prone_area"],
  url: "https://example.org/sms",
};

// A Flood-Prone Area square around HOME, in GeoJSON [lon, lat] order.
const AROUND_HOME = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {},
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-82.33, 29.64],
            [-82.31, 29.64],
            [-82.31, 29.66],
            [-82.33, 29.66],
            [-82.33, 29.64],
          ],
        ],
      },
    },
  ],
};

function stubNode(status: "online" | "mesh_only", officialAlerts: OfficialAlert[]) {
  const answers: Record<string, unknown> = {
    "/api/state": nepalNodeState({ role: "sensor", status, official_alerts: officialAlerts }),
    "/api/cache-pack": { available: true, manifest: null },
    "/api/cache-pack/files/shelters.json": [],
    "/api/cache-pack/files/flood_prone.geojson": AROUND_HOME,
    "/api/shelters": { open: [] },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url in answers ? Response.json(answers[url]) : new Response(null, { status: 404 }),
    ),
  );
}

function saveProfileInsideFloodProneArea() {
  localStorage.setItem(
    PROFILE_KEY,
    JSON.stringify({
      version: 1,
      profile: {
        home: HOME,
        housing: "site-built",
        needsSpecialNeedsShelter: false,
        needsPetFriendlyShelter: false,
      },
    }),
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("Official Alerts show newest first, tagged OFFICIAL · REPLAY with their source", async () => {
  stubNode("online", [NOTICE, RIVERBANK_SMS]);
  render(<App />);

  const alertsPanel = screen.getByRole("region", { name: "Alerts" });
  expect(await within(alertsPanel).findByText(RIVERBANK_SMS.headline)).toBeVisible();
  const cards = within(alertsPanel).getAllByRole("article", { name: "Official Alert" });
  expect(cards.map((card) => within(card).getByRole("heading").textContent)).toEqual([
    RIVERBANK_SMS.headline,
    NOTICE.headline,
  ]);
  expect(within(cards[0]).getByText("OFFICIAL · REPLAY")).toBeVisible();
  expect(within(cards[0]).getByText("DHM")).toBeVisible();
  expect(within(cards[0]).getByText("Issued 26 Aug 2026 · 09:15 NPT")).toBeVisible();
  expect(within(cards[0]).getByRole("link", { name: "Read at the source" })).toHaveAttribute(
    "href",
    RIVERBANK_SMS.url,
  );
});

test("while Mesh-only the source link is replaced by a note", async () => {
  stubNode("mesh_only", [NOTICE]);
  render(<App />);

  const alertsPanel = await screen.findByRole("region", { name: "Alerts" });
  expect(await within(alertsPanel).findByText("Source link opens when online")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Read at the source" })).toBeNull();
});

test("the riverbank alert is marked for a household in the Flood-Prone Area and is in its plan", async () => {
  saveProfileInsideFloodProneArea();
  stubNode("online", [RIVERBANK_SMS]);
  render(<App />);

  const alertsPanel = screen.getByRole("region", { name: "Alerts" });
  expect(await within(alertsPanel).findByText("APPLIES TO YOUR HOUSEHOLD")).toBeVisible();
  const planAlerts = await screen.findByRole("list", {
    name: "Official Alerts for your household",
  });
  expect(within(planAlerts).getByText(/remain on high alert/)).toBeVisible();
});

test("with no Official Alert the panel says why it is empty", async () => {
  stubNode("online", []);
  render(<App />);
  expandPanel("Alerts");

  expect(
    await screen.findByText("No Official Alerts or Community Warnings right now."),
  ).toBeVisible();
});
