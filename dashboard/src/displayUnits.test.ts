import { measurementInDisplayUnit } from "./displayUnits";
import { FAKE_REGION, NEPAL_REGION } from "./fakeNodeState";

const km = NEPAL_REGION.display_units;
const mi = FAKE_REGION.display_units;

test("air temperature and wind speed follow the Region's distance unit", () => {
  const temperature = { value: 21.46, unit: "°C" };
  const wind = { value: 10, unit: "m/s" };
  expect(measurementInDisplayUnit("air_temperature", temperature, km)).toBe("21.5 °C");
  expect(measurementInDisplayUnit("air_temperature", temperature, mi)).toBe("70.6 °F");
  expect(measurementInDisplayUnit("wind_speed", wind, km)).toBe("36 km/h");
  expect(measurementInDisplayUnit("wind_speed", wind, mi)).toBe("22 mph");
});

test("humidity is a percentage and a camera is a picture number", () => {
  expect(measurementInDisplayUnit("humidity", { value: 62, unit: "%" }, mi)).toBe("62 %");
  expect(measurementInDisplayUnit("camera", { value: 57, unit: "pic" }, km)).toBe("Picture 57");
});

test.each([
  ["water_level", { value: 90, unit: "ft" }],
  ["rain_rate", { value: 3, unit: "in/h" }],
  ["air_pressure", { value: 29.9, unit: "inHg" }],
  ["air_temperature", { value: 70, unit: "°F" }],
  ["wind_speed", { value: 31, unit: "km/h" }],
])("%s in a unit other than its wire unit is shown as sent", (kind, measurement) => {
  expect(measurementInDisplayUnit(kind, measurement, mi)).toBe(
    `${measurement.value} ${measurement.unit}`,
  );
});

test("a kind named like an Object property is shown as sent", () => {
  for (const kind of ["constructor", "__proto__", "toString"]) {
    expect(measurementInDisplayUnit(kind, { value: 4, unit: "pic" }, km)).toBe("4 pic");
  }
});
