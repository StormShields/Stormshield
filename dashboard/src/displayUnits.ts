import type { DisplayUnits, Measurement, ReadingKind } from "./nodeState";

// How many of the Node's own units (cm, mm/h, hPa) one display unit is; the flood-warning rules
// send those, and the Region says what residents read.
const PER_DISPLAY_UNIT = {
  cm: 1,
  m: 100,
  ft: 30.48,
  "mm/h": 1,
  "in/h": 25.4,
  hPa: 1,
  inHg: 33.8639,
};
const DECIMALS = { cm: 1, m: 2, ft: 1, "mm/h": 1, "in/h": 2, hPa: 1, inHg: 2 };

type Shown = "water_level" | "rain_rate" | "air_pressure";

// "90 cm", "3 ft", "0.4 in/h": a number the Node measured, written in the Region's unit for it.
export function inDisplayUnit(value: number, kind: Shown, units: DisplayUnits): string {
  const unit = units[kind];
  return `${Number((value / PER_DISPLAY_UNIT[unit]).toFixed(DECIMALS[unit]))} ${unit}`;
}

const MILES_PER_KM = 0.621371;

// "9.7 mi" or "15.6 km" for a distance the Node worked out in kilometres; kilometres until the
// Region is known.
export function distanceInDisplayUnit(
  km: number,
  units: DisplayUnits | null,
  decimals = 1,
): string {
  return units?.distance === "mi"
    ? `${(km * MILES_PER_KM).toFixed(decimals)} mi`
    : `${km.toFixed(decimals)} km`;
}

// "78 km/h" or "48 mph" for a speed the Node worked out in kilometres per hour.
export function speedInDisplayUnit(kmh: number, units: DisplayUnits | null): string {
  return units?.distance === "mi"
    ? `${Math.round(kmh * MILES_PER_KM)} mph`
    : `${Math.round(kmh)} km/h`;
}

// What a Node sends for each kind the dashboard converts, and how the Region's `distance` unit
// writes it. A kind in any other unit, or a kind not listed, is shown as it was sent.
const CONVERSIONS: Partial<
  Record<ReadingKind, { wireUnit: string; shown: (value: number, units: DisplayUnits) => string }>
> = {
  water_level: {
    wireUnit: "cm",
    shown: (value, units) => inDisplayUnit(value, "water_level", units),
  },
  rain_rate: {
    wireUnit: "mm/h",
    shown: (value, units) => inDisplayUnit(value, "rain_rate", units),
  },
  air_pressure: {
    wireUnit: "hPa",
    shown: (value, units) => inDisplayUnit(value, "air_pressure", units),
  },
  air_temperature: {
    wireUnit: "°C",
    shown: (value, units) =>
      units.distance === "mi"
        ? `${Number(((value * 9) / 5 + 32).toFixed(1))} °F`
        : `${Number(value.toFixed(1))} °C`,
  },
  wind_speed: {
    wireUnit: "m/s",
    shown: (value, units) => speedInDisplayUnit(value * 3.6, units),
  },
  camera: { wireUnit: "pic", shown: (value) => `Picture ${value}` },
};

// "3.2 ft", "21 °C", "Picture 57": a Measurement as residents read it. Only a known kind in its
// wire unit is converted; anything else is shown as sent, never as a wrongly converted number.
export function measurementInDisplayUnit(
  kind: ReadingKind,
  measurement: Measurement,
  units: DisplayUnits,
): string {
  const conversion = Object.hasOwn(CONVERSIONS, kind) ? CONVERSIONS[kind] : undefined;
  return conversion && conversion.wireUnit === measurement.unit
    ? conversion.shown(measurement.value, units)
    : `${measurement.value} ${measurement.unit}`;
}
