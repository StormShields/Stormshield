import { kindLabel } from "./ReadingsPanel";

test("the three new kinds and the camera have their labels", () => {
  expect(["air_temperature", "humidity", "wind_speed", "camera"].map(kindLabel)).toEqual([
    "Air temperature",
    "Humidity",
    "Wind speed",
    "Camera",
  ]);
});

test("an unknown kind reads as its own name, even one named like an Object property", () => {
  expect(kindLabel("soil_temperature")).toBe("Soil temperature");
  expect(kindLabel("constructor")).toBe("Constructor");
  expect(kindLabel("__proto__")).toBe("__proto__");
  expect(kindLabel("toString")).toBe("toString");
});
