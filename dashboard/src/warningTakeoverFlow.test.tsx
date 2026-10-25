import { fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { bannerWarnings, pendingWarnings } from "./acknowledgedWarnings";
import type { CommunityWarning } from "./communityWarnings";
import { FAKE_REGION, fakeNodeSnapshot, fakeNodeState } from "./fakeNodeState";
import type { OfficialAlert } from "./officialAlerts";
import { setViewport } from "./fakeViewport";
import { WarningTakeover } from "./WarningTakeover";

const SURGE_T = Date.parse("2026-08-26T02:52:00Z") / 1000;
const ACKNOWLEDGED_KEY = "storm-shield.acknowledged-warnings";

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
const SMS: OfficialAlert = {
  ...NOTICE,
  id: "dhm-sms",
  issued: "2026-08-26T09:15:00+05:45",
  headline: "SMS to riverbank residents: remain on high alert",
};

let answers: { warnings: CommunityWarning[]; alerts: OfficialAlert[] };

function stubNode() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/state") {
        return Response.json(
          fakeNodeState({
            id: "porch",
            community_warnings: answers.warnings,
            official_alerts: answers.alerts,
            nodes: [fakeNodeSnapshot("s0", { name: "S0 Lhende", river_km: -12.2 })],
          }),
        );
      }
      return new Response(null, { status: 404 });
    }),
  );
}

beforeEach(() => {
  answers = { warnings: [], alerts: [] };
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("which warning comes first", () => {
  it("lists Official before Community, each oldest first", () => {
    const order = pendingWarnings([SMS, NOTICE], [WARNING], []).map((each) => each.key);
    expect(order).toEqual(["official:dhm-notice", "official:dhm-sms", "community:7"]);
  });

  it("leaves out what this device already acknowledged, by id", () => {
    const order = pendingWarnings([SMS, NOTICE], [WARNING], ["official:dhm-notice"]);
    expect(order.map((each) => each.key)).toEqual(["official:dhm-sms", "community:7"]);
  });

  it("keeps the newest acknowledged warning of each kind for the banners", () => {
    const done = ["official:dhm-notice", "official:dhm-sms", "community:7"];
    expect(bannerWarnings([NOTICE, SMS], [WARNING], done).map((each) => each.key)).toEqual([
      "official:dhm-sms",
      "community:7",
    ]);
  });
});

// The Takeover is the phone's; a desktop gets the band (warningBandFlow.test.tsx).
describe("the takeover on the page", () => {
  beforeEach(() => setViewport(390));

  it("opens for a Community Warning, with the fixed line and a 64 px Acknowledge", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);

    const takeover = await screen.findByRole("alertdialog");
    expect(
      within(takeover).getByText("FLASH FLOOD · COMMUNITY WARNING · NOT OFFICIAL"),
    ).toBeVisible();
    expect(
      within(takeover).getByText("Check official sources for any evacuation decision."),
    ).toBeVisible();
    expect(within(takeover).queryByText(/of 2/)).toBeNull();
    expect(within(takeover).getByRole("button", { name: "Acknowledge" })).toBeVisible();
  });

  it("shows Official first, then Community, with the count", async () => {
    answers = { warnings: [WARNING], alerts: [NOTICE] };
    stubNode();
    render(<App />);

    const first = await screen.findByRole("alertdialog");
    expect(within(first).getByText("OFFICIAL · REPLAY")).toBeVisible();
    expect(within(first).getByText("1 of 2")).toBeVisible();

    fireEvent.click(within(first).getByRole("button", { name: "Acknowledge" }));
    const second = await screen.findByRole("alertdialog");
    expect(
      within(second).getByText("FLASH FLOOD · COMMUNITY WARNING · NOT OFFICIAL"),
    ).toBeVisible();
    expect(screen.queryByText("1 of 2")).toBeNull();
  });

  it("keeps a banner and the Alerts Panel card after Acknowledge, and does not reopen", async () => {
    answers = { warnings: [], alerts: [NOTICE] };
    stubNode();
    const { unmount } = render(<App />);

    fireEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Acknowledge" }),
    );
    expect(screen.queryByRole("alertdialog")).toBeNull();
    const banner = screen
      .getAllByRole("status")
      .find((each) => /OFFICIAL/.test(each.textContent ?? ""));
    expect(banner).toHaveTextContent(NOTICE.headline);
    expect(JSON.parse(localStorage.getItem(ACKNOWLEDGED_KEY) ?? "[]")).toEqual([
      "official:dhm-notice",
    ]);

    // A reload on the same device: the same warning stays quiet.
    unmount();
    render(<App />);
    expect(await screen.findByRole("tab", { name: /Alerts/ })).toBeVisible();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("opens again for a new warning after an earlier one was acknowledged", async () => {
    answers = { warnings: [], alerts: [NOTICE] };
    localStorage.setItem(ACKNOWLEDGED_KEY, JSON.stringify(["official:dhm-notice"]));
    stubNode();
    render(<App />);
    expect(await screen.findByRole("tab", { name: /Alerts/ })).toBeVisible();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    answers.alerts = [NOTICE, SMS];
    const takeover = await screen.findByRole("alertdialog", {}, { timeout: 3000 });
    expect(within(takeover).getByText(SMS.headline)).toBeVisible();
  });

  it("is a full-screen sheet on a phone", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    expect(await screen.findByRole("alertdialog")).toBeVisible();
    expect(document.querySelector("main")).toHaveClass("phone");
  });
});

describe("a Community Warning's takeover", () => {
  it("leads with the wave countdown", () => {
    render(
      <WarningTakeover
        region={FAKE_REGION}
        pending={[{ kind: "community", key: "community:7", warning: WARNING }]}
        nodes={[fakeNodeSnapshot("s0", { name: "S0 Lhende" })]}
        thisNodeId="porch"
        waveArrival={{ kind: "expected", at: 1_000 + 9 * 60 }}
        eventT={1_000}
        online
        onAcknowledge={() => {}}
      />,
    );
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Wave expected at your home in about 9 min")).toBeVisible();
  });
});

describe("the chime", () => {
  beforeEach(() => setViewport(390));

  class FakeAudioContext {
    static made = 0;
    static notes = 0;
    currentTime = 0;
    destination = {};
    constructor() {
      FakeAudioContext.made += 1;
    }
    createOscillator() {
      FakeAudioContext.notes += 1;
      const oscillator = {
        frequency: { value: 0 },
        connect: (next: unknown) => next,
        start: () => {},
        stop: () => {},
      };
      return oscillator;
    }
    createGain() {
      return {
        gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
        connect: (next: unknown) => next,
      };
    }
    close() {
      return Promise.resolve();
    }
  }

  beforeEach(() => {
    FakeAudioContext.made = 0;
    FakeAudioContext.notes = 0;
    vi.stubGlobal("AudioContext", FakeAudioContext);
  });

  // Order matters: the page counts as tapped for the rest of this file once the second runs.
  it("stays silent on a page nobody has tapped", async () => {
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await screen.findByRole("alertdialog");
    expect(FakeAudioContext.made).toBe(0);
  });

  it("plays two notes once when the takeover opens, and not again for the same warning", async () => {
    fireEvent.pointerDown(window);
    answers.warnings = [WARNING];
    stubNode();
    render(<App />);
    await screen.findByRole("alertdialog");
    expect(FakeAudioContext.made).toBe(1);
    expect(FakeAudioContext.notes).toBe(2);

    await new Promise((resolve) => setTimeout(resolve, 1500));
    expect(FakeAudioContext.made).toBe(1);
  });
});
