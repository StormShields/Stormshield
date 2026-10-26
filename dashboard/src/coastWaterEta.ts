import { inDisplayUnit } from "./displayUnits";
import type { DisplayUnits, Region } from "./nodeState";

// One reading of a Node's water level, stamped with the Event time it was heard at.
export type LevelSample = { t: number; levelCm: number };

export type CoastWaterEta =
  // The level has reached the ground.
  | { kind: "at-ground"; levelCm: number; groundCm: number }
  // Event time (Unix seconds) at which the level reaches the ground, at the rate it is rising now.
  | { kind: "expected"; at: number; levelCm: number; riseCmPerHour: number; groundCm: number };

const SECONDS_PER_HOUR = 3600;

type StormSurge = NonNullable<Region["storm_surge"]>;

// The gain over the last `windowS` seconds of Event time, as a rate per hour. Before a full window
// has been heard it is the gain since the oldest sample. Null when there is no span to measure.
function riseCmPerHour(samples: LevelSample[], windowS: number): number | null {
  const newest = samples.at(-1);
  if (!newest) return null;
  const baseline = samples.filter((sample) => sample.t <= newest.t - windowS).at(-1) ?? samples[0];
  const seconds = newest.t - baseline.t;
  if (seconds <= 0) return null;
  return ((newest.levelCm - baseline.levelCm) / seconds) * SECONDS_PER_HOUR;
}

// The Water ETA of one home on a coast, from its ground height and the history of the nearest
// counting Node's level. Null while the water is not rising by the Region's own measure of rising,
// or when the home stands above every level the High threshold implies.
export function coastWaterEta(
  groundCm: number,
  samples: LevelSample[],
  surge: StormSurge,
  eventT: number,
): CoastWaterEta | null {
  const newest = samples.at(-1);
  if (!newest || groundCm > surge.high_level_cm) return null;
  if (newest.levelCm >= groundCm) {
    return { kind: "at-ground", levelCm: newest.levelCm, groundCm };
  }
  // A level that has not changed for a whole window is no longer rising.
  if (eventT - newest.t > surge.rising_window_s) return null;
  const rate = riseCmPerHour(samples, surge.rising_window_s);
  if (rate === null || rate <= 0) return null;
  const hoursLeft = (groundCm - newest.levelCm) / rate;
  return {
    kind: "expected",
    at: newest.t + hoursLeft * SECONDS_PER_HOUR,
    levelCm: newest.levelCm,
    riseCmPerHour: rate,
    groundCm,
  };
}

function hoursAndMinutes(seconds: number): string {
  const minutes = Math.ceil(seconds / 60);
  const [hours, rest] = [Math.floor(minutes / 60), minutes % 60];
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

// A countdown that has run out reads the same as water already at the ground.
export function coastEtaHasArrived(eta: CoastWaterEta, eventT: number): boolean {
  return eta.kind === "at-ground" || eta.at - eventT <= 0;
}

export function coastEtaLine(eta: CoastWaterEta, eventT: number): string {
  if (eta.kind === "at-ground" || eta.at - eventT <= 0) return "Water is at your ground now";
  return `Water reaches your ground in about ${hoursAndMinutes(eta.at - eventT)}`;
}

// "level 5.1 ft, rising 1.4 ft/h, your ground 8.2 ft": what the line is based on.
export function coastEtaBasis(eta: CoastWaterEta, units: DisplayUnits): string {
  const level = inDisplayUnit(eta.levelCm, "water_level", units);
  const ground = inDisplayUnit(eta.groundCm, "water_level", units);
  if (eta.kind === "at-ground") return `level ${level}, your ground ${ground}`;
  const rise = inDisplayUnit(eta.riseCmPerHour, "water_level", units);
  return `level ${level}, rising ${rise}/h, your ground ${ground}`;
}
