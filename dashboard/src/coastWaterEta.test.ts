import { coastEtaBasis, coastEtaLine, coastWaterEta, type LevelSample } from "./coastWaterEta";
import { FORT_MYERS_REGION } from "./fakeNodeState";

const FT = 30.48;
// Fort Myers' Flood-Prone Area ends at 9 ft; some of these homes stand higher, so the rule that drops
// a home above it has its own tests at the end.
const SURGE = { ...FORT_MYERS_REGION.storm_surge!, flood_prone_below_cm: 12 * FT };
const UNITS = FORT_MYERS_REGION.display_units;
const HOUR = 3600;

// A level that rises steadily to `levelFt` at `T`, `ftPerHour` over the whole window before it.
const T = 10_000;
function risingTo(levelFt: number, ftPerHour: number): LevelSample[] {
  const before = (levelFt - (ftPerHour * SURGE.rising_window_s) / HOUR) * FT;
  return [
    { t: T - SURGE.rising_window_s, levelCm: before },
    { t: T, levelCm: levelFt * FT },
  ];
}

describe("the coast Water ETA", () => {
  it("counts the gap to the ground at the rate of rise", () => {
    // 8.2 ft of ground, 5.1 ft of water rising 1.4 ft/h: 3.1 / 1.4 = 2.21 h.
    const eta = coastWaterEta(8.2 * FT, risingTo(5.1, 1.4), SURGE, T);
    expect(eta).not.toBeNull();
    expect(coastEtaLine(eta!, T)).toBe("Water reaches your ground in about 2 h 13 min");
    expect(coastEtaBasis(eta!, UNITS)).toBe("level 5.1 ft, rising 1.4 ft/h, your ground 8.2 ft");
  });

  it("counts down on the Event clock", () => {
    const eta = coastWaterEta(8.2 * FT, risingTo(5.1, 1.4), SURGE, T)!;
    expect(coastEtaLine(eta, T + HOUR)).toBe("Water reaches your ground in about 1 h 13 min");
    expect(coastEtaLine(eta, T + 2.21 * HOUR)).toMatch(
      /^Water reaches your ground in about \d+ min$/,
    );
  });

  it("reads whole hours and whole minutes plainly", () => {
    const eta = coastWaterEta(7 * FT, risingTo(5, 1), SURGE, T)!;
    expect(coastEtaLine(eta, T)).toBe("Water reaches your ground in about 2 h");
  });

  it("says the water is at the ground once the level reaches it", () => {
    const eta = coastWaterEta(8 * FT, risingTo(8, 1), SURGE, T)!;
    expect(coastEtaLine(eta, T)).toBe("Water is at your ground now");
    expect(coastEtaBasis(eta, UNITS)).toBe("level 8 ft, your ground 8 ft");
  });

  it("says it too when the countdown has run out", () => {
    const eta = coastWaterEta(8.2 * FT, risingTo(5.1, 1.4), SURGE, T)!;
    expect(coastEtaLine(eta, T + 3 * HOUR)).toBe("Water is at your ground now");
  });

  it("has none while the level is falling", () => {
    expect(coastWaterEta(8 * FT, risingTo(5, -1), SURGE, T)).toBeNull();
  });

  it("has none while the level is steady", () => {
    expect(coastWaterEta(8 * FT, risingTo(5, 0), SURGE, T)).toBeNull();
  });

  it("has none with no reading, or with one reading to compare", () => {
    expect(coastWaterEta(8 * FT, [], SURGE, T)).toBeNull();
    expect(coastWaterEta(8 * FT, [{ t: T, levelCm: 5 * FT }], SURGE, T)).toBeNull();
  });

  it("has none once the newest reading is older than the rising window", () => {
    expect(
      coastWaterEta(8 * FT, risingTo(5, 1.4), SURGE, T + SURGE.rising_window_s + 1),
    ).toBeNull();
  });

  it("has none for a home above the Flood-Prone Area", () => {
    expect(coastWaterEta(12.5 * FT, risingTo(5, 1.4), SURGE, T)).toBeNull();
    expect(coastWaterEta(12 * FT, risingTo(5, 1.4), SURGE, T)).not.toBeNull();
  });

  it("gives the spec's 8.2 ft home an ETA at Fort Myers, above its High level but inside the Flood-Prone Area", () => {
    const fortMyers = FORT_MYERS_REGION.storm_surge!;
    expect(coastWaterEta(8.2 * FT, risingTo(5.1, 1.4), fortMyers, T)).not.toBeNull();
    expect(coastWaterEta(9.5 * FT, risingTo(5.1, 1.4), fortMyers, T)).toBeNull();
  });
});
