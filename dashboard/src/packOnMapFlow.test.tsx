import { render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";
import { expandPanel } from "./expandPanel";
import { FAKE_REGION, nepalNodeState } from "./fakeNodeState";
import { sourceData } from "./fakeMaplibre";

const SHELTERS = [
  { id: "gym", name: "Test Gym", pos: [29.66, -82.32], special_needs: true, pet_friendly: false },
  { id: "hall", name: "Town Hall", pos: [29.67, -82.33], special_needs: false, pet_friendly: true },
  {
    id: "school",
    name: "Old School",
    pos: [29.68, -82.34],
    special_needs: false,
    pet_friendly: false,
  },
];

const CORRIDOR = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { source: "APPROXIMATE river corridor" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-82.4, 29.6],
            [-82.4, 29.7],
            [-82.3, 29.7],
            [-82.4, 29.6],
          ],
        ],
      },
    },
  ],
};

function stubNode({
  packAvailable,
  open,
  region,
}: {
  packAvailable: boolean;
  open: string[];
  region?: typeof FAKE_REGION;
}) {
  const answers: Record<string, unknown> = {
    "/api/state": nepalNodeState(region ? { region } : {}),
    "/api/cache-pack": { available: packAvailable, manifest: null },
    "/api/cache-pack/files/shelters.json": SHELTERS,
    "/api/cache-pack/files/flood_prone.geojson": CORRIDOR,
    "/api/shelters": { open },
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

test("every Shelter in the Cache Pack is marked with its name and the flags it has", async () => {
  stubNode({ packAvailable: true, open: ["gym", "hall", "school"] });
  render(<App />);
  expandPanel("Evacuation Plan");

  expect(await screen.findByText("Test Gym · special needs")).toBeVisible();
  expect(await screen.findByText("Town Hall · pets")).toBeVisible();
  expect(await screen.findByText("Old School")).toBeVisible();
  expect(document.querySelectorAll(".shelter-pin")).toHaveLength(3);
});

test("a Shelter the Hub has not announced as open says Closed", async () => {
  stubNode({ packAvailable: true, open: ["hall"] });
  render(<App />);
  expandPanel("Evacuation Plan");

  expect(await screen.findByText("Test Gym · special needs · Closed")).toBeVisible();
  expect(await screen.findByText("Town Hall · pets")).toBeVisible();
  expect(document.querySelectorAll(".shelter-pin.closed")).toHaveLength(2);
});

test("the corridor is drawn and captioned as approximate", async () => {
  stubNode({ packAvailable: true, open: [] });
  render(<App />);
  expandPanel("Evacuation Plan");

  expect(await screen.findByText("Flood-Prone Area: hand-drawn, approximate")).toBeVisible();
  await waitFor(() => expect(sourceData("flood-prone").features).not.toHaveLength(0));
});

test("a coast Region's traced Flood-Prone Area is captioned as traced and approximate", async () => {
  stubNode({ packAvailable: true, open: [], region: FAKE_REGION });
  render(<App />);
  expandPanel("Evacuation Plan");

  expect(
    await screen.findByText("Flood-Prone Area: traced from the terrain, approximate"),
  ).toBeVisible();
  expect(screen.queryByText("Flood-Prone Area: hand-drawn, approximate")).toBeNull();
});

test("the Shelter the plan chose is marked once, apart from the others", async () => {
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
  stubNode({ packAvailable: true, open: ["gym", "hall", "school"] });
  render(<App />);
  expandPanel("Evacuation Plan");

  await screen.findByText(/Nearest open Shelter: Test Gym/);
  await waitFor(() => expect(document.querySelectorAll(".shelter-marker")).toHaveLength(1));
  expect(document.querySelectorAll(".shelter-pin")).toHaveLength(2);
});

test("a Node without a Cache Pack shows no Shelters and no corridor", async () => {
  stubNode({ packAvailable: false, open: [] });
  render(<App />);
  expandPanel("Evacuation Plan");

  await screen.findByRole("region", { name: "Map" });
  expect(document.querySelector(".shelter-pin")).toBeNull();
  expect(sourceData("flood-prone").features).toHaveLength(0);
  expect(screen.queryByText("Flood-Prone Area: hand-drawn, approximate")).toBeNull();
});
