import { inDisplayUnit } from "./displayUnits";
import type { FloodRisk, FloodRiskReason, Hazard, Region } from "./nodeState";

function nodeCount(count: number): string {
  return count === 1 ? "1 Node" : `${count} Nodes`;
}

// A Surge is judged over at most a minute, so seconds is always enough.
function howLong(seconds: number): string {
  return seconds === 0 ? "at once" : `in ${seconds} s`;
}

const waterRose = (rise: string, duration: string) => `water rose ${rise} ${duration}`;

// What a Surge reads like depends on the Hazard; the Node finds none on a coast today.
const SURGE_SENTENCES: Record<Hazard, (rise: string, duration: string) => string> = {
  flash_flood: waterRose,
  storm_surge: waterRose,
};

export function reasonSentence(
  { code, nodes, value, seconds }: FloodRiskReason,
  region: Region,
  hazard: Hazard,
): string {
  const at = `at ${nodeCount(nodes)}`;
  const units = region.display_units;
  switch (code) {
    case "water_surge":
      return SURGE_SENTENCES[hazard](
        inDisplayUnit(value, "water_level", units),
        howLong(seconds ?? 0),
      );
    case "water_high":
      return `water level ${inDisplayUnit(value, "water_level", units)} ${at}`;
    case "water_rising":
      return `water level rising ${at}`;
    case "rain_heavy":
      return `heavy rain: ${inDisplayUnit(value, "rain_rate", units)} ${at}`;
    case "pressure_falling":
      return `low pressure: ${inDisplayUnit(value, "air_pressure", units)} ${at}`;
    case "raining":
      return `soil moisture rising ${at}`;
  }
}

// The map badge already shows the Storm Signal, so the card repeats it only when it is all that
// made Flood Risk appear. A Surge already says the water is rising, so that sentence is dropped.
export function cardReasons(floodRisk: FloodRisk): FloodRiskReason[] {
  if (floodRisk.reasons.length === 1) return floodRisk.reasons;
  const surging = floodRisk.reasons.some((reason) => reason.code === "water_surge");
  return floodRisk.reasons.filter(
    (reason) => reason.code !== "pressure_falling" && !(surging && reason.code === "water_rising"),
  );
}

export function stormSignalSentence(
  { nodes, pressure_hpa }: FloodRisk["storm_signal"],
  region: Region,
): string {
  const pressure =
    pressure_hpa === null
      ? ""
      : `: ${inDisplayUnit(pressure_hpa, "air_pressure", region.display_units)}`;
  return `Low pressure${pressure} at ${nodeCount(nodes)}`;
}
