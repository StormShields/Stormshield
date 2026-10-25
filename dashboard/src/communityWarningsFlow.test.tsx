import { fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { FORT_MYERS_REGION, fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import type { NodeState } from "./nodeState";
import type { OfficialAlert } from "./officialAlerts";

// 08:37 NPT on 26 Aug 2026 is 02:52 UTC.
const SURGE_T = Date.parse("2026-08-26T02:52:00Z") / 1000;

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

const DHM_NOTICE: OfficialAlert = {
  id: "dhm-notice",
  source: "dhm",
  mode: "replay",
  issued: "2026-08-26T09:05:00+05:45",
  headline: "Authorities learn that a major flood has entered the Bhote Koshi",
  applies_to: [],
  url: "https://example.org/notice",
};

// 15:05 EDT on 28 Sep 2022.
const STORM_SURGE_T = Date.parse("2022-09-28T19:05:00Z") / 1000;

const STORM_SURGE_WARNING: CommunityWarning = {
  id: 8,
  t: STORM_SURGE_T + 3,
  hazard: "storm_surge",
  nodes: ["s0"],
  reasons: ["water_high", "water_rising"],
  origin: "s0",
  origin_km: null,
  surge_t: STORM_SURGE_T,
  level_m: 1.5545,
  rise_m_per_h: 0.4267,
};

const FORT_MYERS: Partial<NodeState> = { region: FORT_MYERS_REGION, hazard: "storm_surge" };

function stubNode(
  role: "hub" | "sensor",
  warnings: CommunityWarning[],
  alerts: OfficialAlert[],
  overrides: Partial<NodeState> = {},
) {
  const answers: Record<string, unknown> = {
    "/api/state": fakeNodeState({
      id: "porch",
      role,
      community_warnings: warnings,
      official_alerts: alerts,
      nodes: [
        fakeNodeSnapshot("s0", { name: "S0 Lhende", river_km: -12.2 }),
        fakeNodeSnapshot("porch", { river_km: 0 }),
      ],
      ...overrides,
    }),
    "/api/cache-pack": { available: true, manifest: null },
    "/api/registry": {
      ver: 2,
      nodes: [{ id: "s0", name: "S0 Lhende", status: "registered", last_heard_s: 1 }],
    },
    "/api/warnings": { warnings },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url in answers ? Response.json(answers[url]) : new Response(null, { status: 404 }),
    ),
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("a Community Warning names the Sensor and how far upstream it is, labelled non-official", async () => {
  stubNode("sensor", [WARNING], []);
  render(<App />);

  const card = await screen.findByRole("article", { name: "Community Warning" });
  expect(within(card).getByText("FLASH FLOOD · COMMUNITY WARNING · NOT OFFICIAL")).toBeVisible();
  expect(
    within(card).getByText("Water is surging at S0 Lhende, 12.2 km upstream of this Node"),
  ).toBeVisible();
  expect(within(card).getByText("Signed by the Hub · verified")).toBeVisible();
  expect(
    within(card).getByText("Check official sources for any evacuation decision."),
  ).toBeVisible();
  expect(screen.queryByRole("article", { name: "Official Alert" })).toBeNull();
  expect(within(card).getByRole("link", { name: "Official source: DHM Nepal" })).toHaveAttribute(
    "href",
    "https://www.hydrology.gov.np/",
  );
});

test("the lead-time line compares the warning with the first Official Alert", async () => {
  stubNode("sensor", [WARNING], [DHM_NOTICE]);
  render(<App />);

  expect(
    await screen.findByText("Community Warning 08:37 · first Official Alert 09:05 NPT"),
  ).toBeVisible();
});

test("the Hub Panel's Warnings tab logs what was sent, with the Node and its River km", async () => {
  stubNode("hub", [WARNING], []);
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Warnings" }));

  const log = await within(panel).findByRole("region", { name: "Warning log" });
  expect(within(log).getByText("08:37")).toBeVisible();
  expect(within(log).getByText("S0 Lhende")).toBeVisible();
  expect(within(log).getByText("River km −12.2")).toBeVisible();
  expect(within(log).getByText("Water is surging")).toBeVisible();
});

test("the Warnings tab says so when nothing was sent", async () => {
  stubNode("hub", [], []);
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Warnings" }));

  expect(await within(panel).findByText(/No Community Warning sent yet/)).toBeVisible();
});

test("a storm-surge Community Warning is titled by its Hazard and gives the level and its rise", async () => {
  stubNode("sensor", [STORM_SURGE_WARNING], [], FORT_MYERS);
  render(<App />);

  const card = await screen.findByRole("article", { name: "Community Warning" });
  expect(within(card).getByText("STORM SURGE · COMMUNITY WARNING · NOT OFFICIAL")).toBeVisible();
  expect(
    within(card).getByText("Water at S0 Lhende is 5.1 ft and rising 1.4 ft an hour"),
  ).toBeVisible();
  expect(within(card).queryByText(/River km/)).toBeNull();
});

test("the word Surge never shows alone on a storm-surge screen", async () => {
  stubNode("hub", [STORM_SURGE_WARNING], [], FORT_MYERS);
  render(<App />);
  await screen.findByRole("article", { name: "Community Warning" });
  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Warnings" }));
  await within(panel).findByRole("region", { name: "Warning log" });

  const text = document.body.textContent ?? "";
  expect(text).toMatch(/storm surge/i);
  expect(text).not.toMatch(/(?<!storm\s*)surge/i);
});

test("the Warnings tab logs a storm surge with its level, not a River km", async () => {
  stubNode("hub", [STORM_SURGE_WARNING], [], FORT_MYERS);
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Warnings" }));

  const log = await within(panel).findByRole("region", { name: "Warning log" });
  expect(within(log).getByText("15:05")).toBeVisible();
  expect(within(log).getByText("Water is 5.1 ft and rising 1.4 ft an hour")).toBeVisible();
  expect(within(log).queryByText(/River km/)).toBeNull();
});

test("on a coast the empty Warnings tab says what sends a storm-surge warning", async () => {
  stubNode("hub", [], [], FORT_MYERS);
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Hub" }));
  const panel = screen.getByRole("dialog", { name: "Hub Panel" });
  fireEvent.click(within(panel).getByRole("tab", { name: "Warnings" }));

  expect(
    await within(panel).findByText(
      /One goes out when a Registered Node reports water past the warning height and rising/,
    ),
  ).toBeVisible();
});
