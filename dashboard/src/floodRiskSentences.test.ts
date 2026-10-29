import { NEPAL_REGION } from "./fakeNodeState";
import { reasonSentence, stormSignalSentence } from "./floodRiskSentences";
import type { Region } from "./nodeState";
import { sourceName, type OfficialAlert } from "./officialAlerts";

const FLORIDA: Region = {
  ...NEPAL_REGION,
  display_units: {
    water_level: "ft",
    rain_rate: "in/h",
    soil_moisture: "%",
    air_pressure: "inHg",
    distance: "mi",
  },
  official_alert_sources: [{ tag: "nws", name: "National Weather Service", covers: "Lee County" }],
};

test("a Flood Risk sentence is written in the Region's units", () => {
  const water = { code: "water_high", nodes: 2, value: 304.8 } as const;
  expect(reasonSentence(water, FLORIDA, "flash_flood")).toBe("water level 10 ft at 2 Nodes");
  const rain = { code: "rain_heavy", nodes: 1, value: 25.4 } as const;
  expect(reasonSentence(rain, FLORIDA, "flash_flood")).toBe("heavy rain: 1 in/h at 1 Node");
  const pressure = { code: "pressure_falling", nodes: 3, value: 1000 } as const;
  expect(reasonSentence(pressure, FLORIDA, "flash_flood")).toBe(
    "low pressure: 29.53 inHg at 3 Nodes",
  );
});

test("a Surge sentence is worded for the Hazard and sized in the Region's unit", () => {
  const surge = { code: "water_surge", nodes: 1, value: 304.8, seconds: 8 } as const;
  expect(reasonSentence(surge, FLORIDA, "flash_flood")).toBe("water rose 10 ft in 8 s");
});

test("the Storm Signal reads in the Region's pressure unit", () => {
  expect(stormSignalSentence({ on: true, nodes: 2, pressure_hpa: 995 }, NEPAL_REGION)).toBe(
    "Low pressure: 995 hPa at 2 Nodes",
  );
  expect(stormSignalSentence({ on: true, nodes: 2, pressure_hpa: 1020 }, FLORIDA)).toBe(
    "Low pressure: 30.12 inHg at 2 Nodes",
  );
});

test("an Official Alert is credited to the Region's name for its source", () => {
  const alert = { source: "nws" } as OfficialAlert;
  expect(sourceName(FLORIDA, alert)).toBe("National Weather Service");
  expect(sourceName(NEPAL_REGION, { source: "district" } as OfficialAlert)).toBe(
    "District authorities",
  );
});
