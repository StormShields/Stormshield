import { fakeNodeSnapshot, fakeNodeState, nepalNodeState } from "./fakeNodeState";
import { nodesOnMap } from "./nodesOnMap";

test("a Node shows its water level, position and simulated flag", () => {
  const state = nepalNodeState({
    nodes: [
      fakeNodeSnapshot("garage", { measurements: { water_level: { value: 0.84, unit: "m" } } }),
    ],
  });
  const [node] = nodesOnMap(state);
  expect(node).toMatchObject({ waterLevelCm: 84, position: [29.652, -82.324], simulated: true });
});

test("a kind the dashboard has no label for is carried with its own unit", () => {
  const state = nepalNodeState({
    nodes: [
      fakeNodeSnapshot("garage", {
        measurements: {
          water_level: { value: 0.84, unit: "m" },
          wind_speed: { value: 31, unit: "km/h" },
        },
      }),
    ],
  });
  const [node] = nodesOnMap(state);
  expect(node.measurements).toEqual([
    { kind: "water_level", value: 84, unit: "cm", shown: "84 cm" },
    { kind: "wind_speed", value: 31, unit: "km/h", shown: "31 km/h" },
  ]);
});

test("this Node is labeled with its name and every other Node with its id", () => {
  const state = nepalNodeState({
    id: "b7e1f40a92c5",
    name: "porch",
    nodes: [fakeNodeSnapshot("91c2e0b47a3d"), fakeNodeSnapshot("b7e1f40a92c5")],
  });
  expect(nodesOnMap(state).map((node) => node.label)).toEqual(["porch", "91c2e0b47a3d"]);
});

test("a Node is stale and old exactly as the Node says, with no threshold of its own", () => {
  const state = nepalNodeState({
    nodes: [
      fakeNodeSnapshot("fresh", { age_s: 16, stale: false }),
      fakeNodeSnapshot("silent", { age_s: 3, stale: true }),
    ],
  });
  const [fresh, silent] = nodesOnMap(state);
  expect(fresh).toMatchObject({ stale: false, ageSeconds: 16 });
  expect(silent).toMatchObject({ stale: true, ageSeconds: 3 });
});

test("a Node carries its level from Flood Risk, and no level when Flood Risk has none", () => {
  const state = nepalNodeState({
    flood_risk: { ...nepalNodeState().flood_risk, nodes: { garage: "high" } },
    nodes: [fakeNodeSnapshot("garage"), fakeNodeSnapshot("porch")],
  });
  expect(nodesOnMap(state).map((node) => node.level)).toEqual([null, "high"]);
});

test("before the first answer there are no Nodes on the map", () => {
  expect(nodesOnMap(null)).toEqual([]);
});

test("a Registered Node is labeled with its registry name, an Unverified one with its id", () => {
  const state = nepalNodeState({
    id: "b7e1f40a92c5",
    nodes: [
      fakeNodeSnapshot("91c2e0b47a3d", { name: "kitchen" }),
      fakeNodeSnapshot("c0ffee000000", { registered: false, name: null }),
    ],
  });
  expect(nodesOnMap(state).map((node) => node.label)).toEqual(["kitchen", "c0ffee000000"]);
});

test("this Node comes first, then Registered Nodes A to Z, then Unverified Nodes", () => {
  const state = nepalNodeState({
    id: "bbb",
    name: "porch",
    nodes: [
      fakeNodeSnapshot("ccc", { registered: false, name: null }),
      fakeNodeSnapshot("aaa", { name: "shed" }),
      fakeNodeSnapshot("bbb", { name: "porch" }),
      fakeNodeSnapshot("ddd", { name: "garage" }),
    ],
  });
  expect(nodesOnMap(state).map((node) => node.label)).toEqual(["porch", "garage", "shed", "ccc"]);
});

test("the new kinds are shown in the Region's units, and a camera as a picture number", () => {
  const measurements = {
    air_temperature: { value: 30, unit: "°C" },
    humidity: { value: 80, unit: "%" },
    wind_speed: { value: 10, unit: "m/s" },
    camera: { value: 57, unit: "pic" },
  };
  const shown = (state: ReturnType<typeof nepalNodeState>) =>
    nodesOnMap({
      ...state,
      nodes: [fakeNodeSnapshot("mast", { measurements })],
    })[0].measurements.map((measurement) => measurement.shown);
  expect(shown(nepalNodeState())).toEqual(["30 °C", "80 %", "36 km/h", "Picture 57"]);
  expect(shown(fakeNodeState())).toEqual(["86 °F", "80 %", "22 mph", "Picture 57"]);
});

test("a known kind in a non-wire unit and a kind named constructor are shown as sent", () => {
  const state = nepalNodeState({
    nodes: [
      fakeNodeSnapshot("mast", {
        measurements: JSON.parse(
          '{"rain_rate":{"value":2,"unit":"in/h"},"constructor":{"value":3,"unit":"x"},"__proto__":{"value":4,"unit":"y"}}',
        ),
      }),
    ],
  });
  expect(nodesOnMap(state)[0].measurements.map((m) => [m.kind, m.shown])).toEqual([
    ["rain_rate", "2 in/h"],
    ["constructor", "3 x"],
    ["__proto__", "4 y"],
  ]);
});
