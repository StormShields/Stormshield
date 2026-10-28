import { inDisplayUnit } from "./displayUnits";
import type { DisplayUnits, OfficialGauge } from "./nodeState";
import { regionClockTime, regionZoneLabel } from "./regionTime";

// "NOAA 8725520 · 2.3 ft · 09:12 EDT": who measured, what, and when, so it is never mistaken for a
// Community Reading. Before the Hub has sent a level it says so instead of showing a number.
export function officialGaugeLabel(
  gauge: OfficialGauge,
  units: DisplayUnits,
  timeZone: string,
): string {
  const name = `${gauge.agency} ${gauge.station}`;
  if (gauge.level_m === null || gauge.observed === null) return `${name} · no level yet`;
  const level = inDisplayUnit(gauge.level_m * 100, "water_level", units);
  const at = `${regionClockTime(gauge.observed, timeZone)} ${regionZoneLabel(gauge.observed, timeZone)}`;
  return `${name} · ${level} · ${at}`;
}
