import { NEPAL_REGION } from "./fakeNodeState";
import { measuredSpeedLine, type FlashFloodWarning } from "./communityWarnings";
import {
  MAX_DISTANCE_TO_RIVER_KM,
  parseRiverLine,
  riverKmOfHome,
  waveArrival,
  waveEtaLine,
  waveFrontKm,
  type RiverLine,
} from "./waveEta";

// A straight north-to-south river at lon 85, one vertex per km (0.009 degrees of latitude is
// about 1 km): 190 km/h down to km 0, then 60 km/h to km 30.
const RIVER: RiverLine = [
  {
    speedKmh: 190,
    km: [-10, -5, 0],
    points: [
      [28.09, 85],
      [28.045, 85],
      [28, 85],
    ],
  },
  {
    speedKmh: 60,
    km: [0, 10, 20, 30],
    points: [
      [28, 85],
      [27.91, 85],
      [27.82, 85],
      [27.73, 85],
    ],
  },
];

const SURGE_T = 1_787_716_020;

function warningAt(originKm: number, surgeT = SURGE_T): FlashFloodWarning {
  return {
    id: 1,
    t: surgeT,
    nodes: ["s0"],
    hazard: "flash_flood",
    reasons: ["water_surge"],
    origin: "s0",
    origin_km: originKm,
    surge_t: surgeT,
  };
}

const at = (km: number, offsetDegrees = 0) => ({ lat: 28 - km * 0.009, lon: 85 + offsetDegrees });

describe("the wave's ETA at home", () => {
  it("adds up each reach's time from the origin's River km to home", () => {
    // -10 to 0 at 190 km/h, then 0 to 20 at 60 km/h.
    const seconds = (10 / 190 + 20 / 60) * 3600;
    const arrival = waveArrival(RIVER, at(20), [warningAt(-10)]);
    expect(arrival?.kind === "expected" && arrival.at).toBeCloseTo(SURGE_T + seconds, 0);
  });

  it("counts only the reach a home is in when the origin is in the same reach", () => {
    const arrival = waveArrival(RIVER, at(20), [warningAt(10)]);
    expect(arrival?.kind === "expected" && arrival.at).toBeCloseTo(SURGE_T + (10 / 60) * 3600, 0);
  });

  it("gives a home upstream of the origin no ETA", () => {
    expect(waveArrival(RIVER, at(-5), [warningAt(0)])).toBeNull();
    expect(waveArrival(RIVER, at(10), [warningAt(10)])).toBeNull();
  });

  it("follows the earliest arrival and ignores origins below home", () => {
    // From km -10 the wave needs about 1990 s to reach km 30; the second Surge, 60 s later at
    // km 20, needs 10 km at 60 km/h = 600 s, so it is the one to count down to.
    const second = warningAt(20, SURGE_T + 60);
    expect(waveArrival(RIVER, at(30), [warningAt(-10), second])).toEqual({
      kind: "expected",
      at: SURGE_T + 660,
    });
    const belowHome = waveArrival(RIVER, at(10), [warningAt(20), warningAt(0)]);
    const upstreamOnly = waveArrival(RIVER, at(10), [warningAt(0)]);
    expect(belowHome).toEqual(upstreamOnly);
  });

  it("has nothing to say before any warning", () => {
    expect(waveArrival(RIVER, at(20), [])).toBeNull();
  });

  it("says the home is not near the river when it is beyond the limit", () => {
    expect(riverKmOfHome(RIVER, at(20, 0.001))).toBe(20);
    const farLonOffset = (MAX_DISTANCE_TO_RIVER_KM + 1) / (111.32 * Math.cos((28 * Math.PI) / 180));
    expect(riverKmOfHome(RIVER, at(20, farLonOffset))).toBeNull();
    expect(waveArrival(RIVER, at(20, farLonOffset), [warningAt(-10)])).toEqual({
      kind: "not-near-river",
    });
  });
});

describe("the countdown line", () => {
  it("rounds minutes up", () => {
    expect(waveEtaLine(1000 + 9 * 60 - 20, 1000)).toBe("Wave expected at your home in about 9 min");
    expect(waveEtaLine(1000 + 1, 1000)).toBe("Wave expected at your home in about 1 min");
  });

  it("says the wave is expected now at zero and never goes negative", () => {
    expect(waveEtaLine(1000, 1000)).toBe("Wave expected now");
    expect(waveEtaLine(1000, 5000)).toBe("Wave expected now");
  });
});

describe("reading the pack's river line", () => {
  it("turns each GeoJSON reach into lat/lon points with their River km", () => {
    const river = parseRiverLine({
      features: [
        {
          properties: { speed_kmh: 68, km: [0, 1] },
          geometry: {
            coordinates: [
              [85.1, 28.1],
              [85.2, 28.2],
            ],
          },
        },
      ],
    });
    expect(river).toEqual([
      {
        speedKmh: 68,
        km: [0, 1],
        points: [
          [28.1, 85.1],
          [28.2, 85.2],
        ],
      },
    ]);
  });

  it("refuses a reach whose km list does not match its vertices", () => {
    expect(() =>
      parseRiverLine({
        features: [
          {
            properties: { speed_kmh: 68, km: [0] },
            geometry: {
              coordinates: [
                [1, 2],
                [3, 4],
              ],
            },
          },
        ],
      }),
    ).toThrow(/river.geojson/);
  });
});

describe("the measured wave speed", () => {
  // The second Node sits at km 10 and surged 1000 s after the origin; the wave took 20 km in
  // 1000 s between them, and 120 km/h from there on.
  const measured = { node: "s1", km: 10, surge_t: SURGE_T + 1000, speed_kmh: 120 };
  const measuredWarning = { ...warningAt(-10), measured };

  it("replaces the reconstructed speeds below the second Node, counted from its Surge", () => {
    const arrival = waveArrival(RIVER, at(20), [measuredWarning]);
    expect(arrival?.kind === "expected" && arrival.at).toBeCloseTo(
      SURGE_T + 1000 + (10 / 120) * 3600,
      0,
    );
  });

  it("keeps the reconstructed speeds for a home above the second Node", () => {
    const seconds = (10 / 190) * 3600;
    const arrival = waveArrival(RIVER, at(0), [measuredWarning]);
    expect(arrival?.kind === "expected" && arrival.at).toBeCloseTo(SURGE_T + seconds, 0);
  });

  it("gives a home upstream of the origin no ETA, measured or not", () => {
    expect(waveArrival(RIVER, at(-10), [{ ...measuredWarning, origin_km: -5 }])).toBeNull();
  });
});

describe("the measured speed line", () => {
  const names: Record<string, string> = { s0: "S0", s1: "S1" };
  const nameOf = (id: string) => names[id] ?? id;

  it("shows distance, time and speed with the two Nodes' names", () => {
    const warning = {
      ...warningAt(-5.6),
      measured: { node: "s1", km: 10, surge_t: SURGE_T + 720, speed_kmh: 78 },
    };
    expect(measuredSpeedLine(warning, nameOf, NEPAL_REGION.display_units)).toBe(
      "Measured: 15.6 km in 12 min = 78 km/h (S0 to S1)",
    );
  });

  it("is absent until a second Node has surged", () => {
    expect(measuredSpeedLine(warningAt(-5.6), nameOf, NEPAL_REGION.display_units)).toBeNull();
  });
});

describe("waveFrontKm", () => {
  it("is null until a warning's Surge has started", () => {
    expect(waveFrontKm(RIVER, [], SURGE_T + 60)).toBeNull();
    expect(waveFrontKm(RIVER, [warningAt(-10)], SURGE_T - 1)).toBeNull();
  });

  it("follows the reach speeds down the river", () => {
    // 190 km/h from km -10 reaches km 0 after 189.5 s; then 60 km/h reaches km 10 after 600 s more.
    expect(waveFrontKm(RIVER, [warningAt(-10)], SURGE_T + 94.7)).toBeCloseTo(-5, 1);
    expect(waveFrontKm(RIVER, [warningAt(-10)], SURGE_T + 789.5)).toBeCloseTo(10, 1);
  });

  it("stops at the end of the river", () => {
    expect(waveFrontKm(RIVER, [warningAt(-10)], SURGE_T + 100_000)).toBeCloseTo(30, 1);
  });

  it("reports the furthest front when two warnings are running", () => {
    const fronts = waveFrontKm(RIVER, [warningAt(-10), warningAt(10)], SURGE_T + 789.5);
    expect(fronts).toBeGreaterThan(10.5);
  });
});
