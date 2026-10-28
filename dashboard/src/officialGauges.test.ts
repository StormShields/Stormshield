import { FORT_MYERS_REGION } from "./fakeNodeState";
import type { OfficialGauge } from "./nodeState";
import { officialGaugeLabel } from "./officialGauges";

const GAUGE: OfficialGauge = {
  agency: "NOAA",
  station: "8725520",
  label: "Fort Myers (NOAA tide gauge)",
  pos: [26.64778, -81.87111],
  level_m: 1,
  // 28 Sep 2022, 22:30 UTC: 18:30 in Eastern time.
  observed: Date.UTC(2022, 8, 28, 22, 30) / 1000,
  mode: "live",
};

describe("officialGaugeLabel", () => {
  it("names the agency and station, the level in the Region's unit and the time in its zone", () => {
    expect(
      officialGaugeLabel(GAUGE, FORT_MYERS_REGION.display_units, FORT_MYERS_REGION.time_zone),
    ).toBe("NOAA 8725520 · 3.3 ft · 18:30 EDT");
  });

  it("marks a recorded level REPLAY, so it is never mistaken for today's", () => {
    expect(
      officialGaugeLabel(
        { ...GAUGE, mode: "replay" },
        FORT_MYERS_REGION.display_units,
        FORT_MYERS_REGION.time_zone,
      ),
    ).toBe("REPLAY · NOAA 8725520 · 3.3 ft · 18:30 EDT");
  });

  it("says there is no level yet before the Hub has sent one", () => {
    expect(
      officialGaugeLabel(
        { ...GAUGE, level_m: null, observed: null, mode: null },
        FORT_MYERS_REGION.display_units,
        FORT_MYERS_REGION.time_zone,
      ),
    ).toBe("NOAA 8725520 · no level yet");
  });
});
