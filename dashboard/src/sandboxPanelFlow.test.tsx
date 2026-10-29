import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";
import type { CommunityWarning } from "./communityWarnings";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { dragMarker, markerAt, sourceData, tapMap } from "./fakeMaplibre";
import type { SandboxNode, SandboxNodes } from "./useSandboxNodes";

const HUB_AT: [number, number] = [27.97, 85.18];
const NEAR_AT: [number, number] = [27.92, 85.14];
const FAR_AT: [number, number] = [28.25, 85.37];
const WIDE_RANGE_M = 40_000;
const NARROW_RANGE_M = 10_000;

function node(
  id: string,
  position: [number, number],
  overrides: Partial<SandboxNode> = {},
): SandboxNode {
  return {
    id,
    name: id,
    role: "sensor",
    position,
    links: [],
    hops: 1,
    heard_warning: false,
    ...overrides,
  };
}

// Everyone in range of the Hub.
const WIDE: SandboxNodes = {
  radio_range_m: WIDE_RANGE_M,
  suggested_sites: [],
  nodes: [
    node("hub", HUB_AT, { role: "hub", hops: 0, links: ["near", "far"] }),
    node("near", NEAR_AT, { links: ["hub"] }),
    node("far", FAR_AT, { links: ["hub"] }),
  ],
};

// The range cut to the Hub's one near neighbour: "far" has no path left.
const NARROW: SandboxNodes = {
  radio_range_m: NARROW_RANGE_M,
  suggested_sites: [],
  nodes: [
    node("hub", HUB_AT, { role: "hub", hops: 0, links: ["near"] }),
    node("near", NEAR_AT, { links: ["hub"] }),
    node("far", FAR_AT, { hops: null }),
  ],
};

let posted: { path: string; body: unknown }[];
let sent: { method: string; path: string; body: unknown }[];
let listed: string[];

function stubTheHub(options: {
  sandbox: boolean;
  answer?: SandboxNodes;
  afterSetting?: SandboxNodes;
  // What the Hub answers to adding, moving or removing a Sensor; a number refuses with that status.
  afterChange?: SandboxNodes | number;
  warnings?: CommunityWarning[];
  // Give the Hub the readings of the Nodes it lists, so each is drawn on the map.
  heardNodes?: boolean;
}) {
  posted = [];
  sent = [];
  listed = [];
  let current = options.answer ?? WIDE;
  vi.stubGlobal("fetch", async (path: string, init?: RequestInit) => {
    if (path === "/api/sandbox/nodes") {
      listed.push(path);
      return Response.json(current);
    }
    if (path === "/api/sandbox/radio-range" && init?.method === "POST") {
      posted.push({ path, body: JSON.parse(init.body as string) });
      current = options.afterSetting ?? current;
      return Response.json(current);
    }
    if (path.startsWith("/api/sandbox/sensors")) {
      sent.push({
        method: init?.method ?? "GET",
        path,
        body: init?.body ? JSON.parse(init.body as string) : undefined,
      });
      const answer = options.afterChange ?? current;
      if (typeof answer === "number") {
        return Response.json({ detail: "the Hub said no" }, { status: answer });
      }
      current = answer;
      return Response.json(current);
    }
    if (path === "/api/state") {
      return Response.json(
        nepalNodeState({
          id: "hub",
          name: "hub",
          sandbox: options.sandbox ? { label: "SIMULATED" } : null,
          // Where the readings say, which is not quite where the Node is.
          nodes: options.heardNodes
            ? WIDE.nodes.map((each) =>
                fakeNodeSnapshot(each.id, {
                  position: [each.position[0] + 0.001, each.position[1]],
                }),
              )
            : [],
          community_warnings: options.warnings ?? [],
        }),
      );
    }
    return new Response(null, { status: 404 });
  });
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function sandboxPanel() {
  render(<App />);
  return await screen.findByRole("region", { name: "Sandbox" });
}

// How far north of its centre a circle reaches, in metres.
function radiusOf(circle: GeoJSON.Feature): number {
  const [[...ring]] = (circle.geometry as GeoJSON.Polygon).coordinates;
  const latitudes = ring.map(([, lat]) => lat);
  return ((Math.max(...latitudes) - Math.min(...latitudes)) / 2) * 111_320;
}

test("outside the Sandbox there is no Sandbox Panel and the Node never gets asked about one", async () => {
  stubTheHub({ sandbox: false });
  render(<App />);
  await screen.findByRole("button", { name: "Hub" });
  expect(screen.queryByRole("region", { name: "Sandbox" })).not.toBeInTheDocument();
  expect(listed).toEqual([]);
});

test("the Panel lists each Node's hops to the Hub, and a Sensor with none is marked on the list and the map", async () => {
  stubTheHub({ sandbox: true, answer: NARROW });
  const panel = await sandboxPanel();
  const rows = await within(panel).findAllByRole("listitem");
  expect(rows.map((row) => row.textContent)).toEqual([
    "hubHubno warning yet",
    "near1 hop to Hubno warning yetRemove",
    "farno path to Hubno warning yetRemove",
  ]);
  // The list says it, and so does the marker pinned to the Sensor on the map.
  expect(await screen.findAllByText("no path to Hub")).toHaveLength(2);
});

test("a Node that heard the latest warning is ticked, and one that did not is not", async () => {
  const warned: SandboxNodes = {
    ...NARROW,
    nodes: NARROW.nodes.map((each) => ({ ...each, heard_warning: each.id !== "far" })),
  };
  const warning: CommunityWarning = {
    id: 1,
    t: 0,
    nodes: ["near"],
    hazard: "flash_flood",
    reasons: ["water_surge"],
    origin: "near",
    origin_km: 3,
    surge_t: 0,
  };
  stubTheHub({ sandbox: true, answer: warned, warnings: [warning] });
  const panel = await sandboxPanel();
  expect(await within(panel).findByText("has not heard the warning")).toBeInTheDocument();
  expect(within(panel).getAllByText("heard the warning")).toHaveLength(2);
});

test("the map draws a circle for every Node at the radio range, and a line between Nodes in range", async () => {
  stubTheHub({ sandbox: true });
  await sandboxPanel();
  await waitFor(() => expect(sourceData("radio-range").features).toHaveLength(3));
  for (const circle of sourceData("radio-range").features) {
    expect(radiusOf(circle)).toBeCloseTo(WIDE_RANGE_M, -2);
  }
  expect(sourceData("radio-links").features).toHaveLength(2);
});

test("moving the slider sends the range to the Sandbox, and the circles, links and hops follow", async () => {
  stubTheHub({ sandbox: true, afterSetting: NARROW });
  const panel = await sandboxPanel();
  const slider = await within(panel).findByRole("slider", { name: "Radio range" });
  expect(slider).toHaveValue("40");

  fireEvent.change(slider, { target: { value: "10" } });

  expect(posted).toEqual([{ path: "/api/sandbox/radio-range", body: { radio_range_m: 10000 } }]);
  await waitFor(() => expect(sourceData("radio-links").features).toHaveLength(1));
  for (const circle of sourceData("radio-range").features) {
    expect(radiusOf(circle)).toBeCloseTo(NARROW_RANGE_M, -2);
  }
  expect(await within(panel).findByText("no path to Hub")).toBeInTheDocument();
  expect(within(panel).getByText("10.0 km")).toBeInTheDocument();
});

test("a range the Hub refuses is reported, not swallowed", async () => {
  stubTheHub({ sandbox: true });
  const panel = await sandboxPanel();
  const slider = await within(panel).findByRole("slider", { name: "Radio range" });
  vi.stubGlobal("fetch", async (path: string) =>
    path === "/api/sandbox/radio-range"
      ? Response.json({ detail: "range must be above zero" }, { status: 422 })
      : Response.json(WIDE),
  );

  fireEvent.change(slider, { target: { value: "0.1" } });

  expect(await within(panel).findByRole("alert")).toHaveTextContent(
    "Could not set the radio range: range must be above zero",
  );
});

// A Node's label on the map, which is what a person drags.
async function mapLabel(name: string): Promise<HTMLElement> {
  return await within(await screen.findByRole("region", { name: "Map" })).findByText(name);
}

const MOVED_NEAR_AT: [number, number] = [28.0, 85.2];
const WITH_NEAR_MOVED: SandboxNodes = {
  ...WIDE,
  nodes: WIDE.nodes.map((each) =>
    each.id === "near" ? { ...each, position: MOVED_NEAR_AT } : each,
  ),
};
const WITH_A_NEW_SENSOR: SandboxNodes = {
  ...WIDE,
  nodes: [...WIDE.nodes, node("s4", [28.1, 85.25], { links: ["hub"] })],
};

test("Add Sensor, then a tap on the map, adds a Sensor there, once", async () => {
  stubTheHub({ sandbox: true, afterChange: WITH_A_NEW_SENSOR });
  const panel = await sandboxPanel();
  const add = within(panel).getByRole("button", { name: "Add Sensor" });

  tapMap(28.1, 85.25);
  expect(sent).toEqual([]);

  fireEvent.click(add);
  expect(add).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Tap the map to place a Sensor")).toBeInTheDocument();
  tapMap(28.1, 85.25);

  await waitFor(() =>
    expect(sent).toEqual([
      { method: "POST", path: "/api/sandbox/sensors", body: { latitude: 28.1, longitude: 85.25 } },
    ]),
  );
  expect(add).toHaveAttribute("aria-pressed", "false");
  expect(await within(panel).findByText("s4")).toBeInTheDocument();
  expect(sourceData("radio-range").features).toHaveLength(4);
  tapMap(28.2, 85.3);
  expect(sent).toHaveLength(1);
});

test("a placing started by mistake is cancelled without adding anything", async () => {
  stubTheHub({ sandbox: true });
  const panel = await sandboxPanel();

  fireEvent.click(within(panel).getByRole("button", { name: "Add Sensor" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  tapMap(28.1, 85.25);

  expect(within(panel).getByRole("button", { name: "Add Sensor" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  expect(sent).toEqual([]);
});

test("a Sensor is drawn where it truly is, and dragging it sends where it was dropped", async () => {
  stubTheHub({ sandbox: true, heardNodes: true, afterChange: WITH_NEAR_MOVED });
  await sandboxPanel();
  const near = await mapLabel("near");
  expect(markerAt(near)).toEqual(NEAR_AT);

  dragMarker(near, 28.0, 85.2);

  await waitFor(() =>
    expect(sent).toEqual([
      {
        method: "PUT",
        path: "/api/sandbox/sensors/near",
        body: { latitude: 28.0, longitude: 85.2 },
      },
    ]),
  );
  // The circle, the link and the marker all follow the answer.
  await waitFor(() => expect(markerAt(near)).toEqual(MOVED_NEAR_AT));
  const centres = sourceData("radio-range").features.map((circle) => {
    const ring = (circle.geometry as GeoJSON.Polygon).coordinates[0];
    return Math.max(...ring.map(([, lat]) => lat));
  });
  expect(centres).toContainEqual(expect.closeTo(28.0 + WIDE_RANGE_M / 111_320, 3));
});

test("the Hub cannot be dragged", async () => {
  stubTheHub({ sandbox: true, heardNodes: true });
  await sandboxPanel();
  const hub = await mapLabel("hub");

  expect(() => dragMarker(hub, 28.0, 85.2)).toThrow("not draggable");
});

test("a drop the Hub refuses is reported and the Sensor goes back", async () => {
  stubTheHub({ sandbox: true, heardNodes: true, afterChange: 409 });
  const panel = await sandboxPanel();
  const near = await mapLabel("near");

  dragMarker(near, 28.0, 85.2);

  expect(await within(panel).findByRole("alert")).toHaveTextContent(
    "Could not move the Sensor: the Hub said no",
  );
  await waitFor(() => expect(markerAt(near)).toEqual(NEAR_AT));
});

test("Remove takes a Sensor off the list and the map, and the Hub has no Remove", async () => {
  const withoutNear: SandboxNodes = {
    ...WIDE,
    nodes: WIDE.nodes.filter((each) => each.id !== "near").map((each) => ({ ...each, links: [] })),
  };
  // The Hub's readings still list "near", as they do for a Node that went quiet.
  stubTheHub({ sandbox: true, heardNodes: true, afterChange: withoutNear });
  const panel = await sandboxPanel();
  const map = await screen.findByRole("region", { name: "Map" });
  await within(map).findByText("near");
  expect(await within(panel).findAllByRole("button", { name: /^Remove / })).toHaveLength(2);
  expect(within(panel).queryByRole("button", { name: "Remove hub" })).not.toBeInTheDocument();

  fireEvent.click(within(panel).getByRole("button", { name: "Remove near" }));

  await waitFor(() =>
    expect(sent).toEqual([
      { method: "DELETE", path: "/api/sandbox/sensors/near", body: undefined },
    ]),
  );
  await waitFor(() => expect(within(panel).queryByText("near")).not.toBeInTheDocument());
  expect(within(map).queryByText("near")).not.toBeInTheDocument();
  expect(sourceData("radio-range").features).toHaveLength(2);
});

const BAY_SITE = {
  label: "Coconut Point",
  why: "Ian's surge came up the bay here",
  position: [28.05, 85.3] as [number, number],
};
const WITH_A_SUGGESTED_SITE: SandboxNodes = { ...WIDE, suggested_sites: [BAY_SITE] };
const WITH_THE_SITE_TAKEN: SandboxNodes = {
  ...WIDE,
  nodes: [...WIDE.nodes, node("s4", BAY_SITE.position, { links: ["hub"] })],
};

test("a suggested site shows its label and why, and a tap on it adds a Sensor there", async () => {
  stubTheHub({
    sandbox: true,
    answer: WITH_A_SUGGESTED_SITE,
    afterChange: WITH_THE_SITE_TAKEN,
  });
  await sandboxPanel();
  const marker = await screen.findByRole("button", { name: "Add a Sensor at Coconut Point" });
  expect(marker).toHaveTextContent("Ian's surge came up the bay here");

  fireEvent.click(marker);

  await waitFor(() =>
    expect(sent).toEqual([
      { method: "POST", path: "/api/sandbox/sensors", body: { latitude: 28.05, longitude: 85.3 } },
    ]),
  );
  // The site is a Sensor now, so its faint marker is gone; removing the Sensor brings it back.
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Add a Sensor at Coconut Point" })).toBeNull(),
  );
});

test("removing a Sensor from a suggested site brings the faint marker back", async () => {
  stubTheHub({ sandbox: true, answer: WITH_THE_SITE_TAKEN, afterChange: WITH_A_SUGGESTED_SITE });
  const panel = await sandboxPanel();
  expect(screen.queryByRole("button", { name: "Add a Sensor at Coconut Point" })).toBeNull();

  fireEvent.click(await within(panel).findByRole("button", { name: "Remove s4" }));

  expect(
    await screen.findByRole("button", { name: "Add a Sensor at Coconut Point" }),
  ).toBeInTheDocument();
});
