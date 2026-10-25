import type { FlashFloodWarning } from "./communityWarnings";
import { waveArrival, type RiverLine } from "./waveEta";
import {
  WAVE_FLASH_SECONDS,
  WAVE_TRAIL_KM,
  nodesTheWavePassed,
  townsTheWaveReached,
  waveFront,
} from "./waveFront";

// A straight north-to-south river at lon 85, one vertex per 5 or 10 km (0.009 degrees of latitude
// is about 1 km): 190 km/h down to km 0, then 60 km/h to km 30.
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
const lat = (km: number) => 28 - km * 0.009;
const TEN_KM_AT = SURGE_T + (10 / 190) * 3600 + (10 / 60) * 3600;

const WARNING: FlashFloodWarning = {
  id: 1,
  t: SURGE_T,
  nodes: ["s0"],
  hazard: "flash_flood",
  reasons: ["water_surge"],
  origin: "s0",
  origin_km: -10,
  surge_t: SURGE_T,
};

describe("the wave front's position on the Event clock", () => {
  it("is not there before a Surge exists or the moment it starts", () => {
    expect(waveFront(RIVER, [], SURGE_T + 600)).toBeNull();
    expect(waveFront(RIVER, [WARNING], SURGE_T)).toBeNull();
  });

  it("runs at the first reach's speed, then the next one's, then stops at the river's end", () => {
    // 60 s at 190 km/h is 3.17 km down from km -10.
    const early = waveFront(RIVER, [WARNING], SURGE_T + 60);
    expect(early?.head[0]).toBeCloseTo(lat(-10 + (190 * 60) / 3600), 3);
    // 189.5 s reach km 0; 600 s more at 60 km/h is km 10.
    const later = waveFront(RIVER, [WARNING], SURGE_T + (10 / 190) * 3600 + 600);
    expect(later?.head[0]).toBeCloseTo(lat(10), 3);
    const after = waveFront(RIVER, [WARNING], SURGE_T + 100_000);
    expect(after?.head[0]).toBeCloseTo(lat(30), 3);
  });

  it("trails 15 km behind the head, and no further back than the origin", () => {
    const later = waveFront(RIVER, [WARNING], SURGE_T + (10 / 190) * 3600 + 600);
    expect(WAVE_TRAIL_KM).toBe(15);
    expect(later?.trail[0][0]).toBeCloseTo(lat(10 - WAVE_TRAIL_KM), 3);
    expect(later?.trail.at(-1)).toEqual(later?.head);
    const early = waveFront(RIVER, [WARNING], SURGE_T + 60);
    expect(early?.trail[0][0]).toBeCloseTo(lat(-10), 3);
  });

  it("reaches a town when that town's ETA runs out", () => {
    const town = { name: "Betrawati", kind: "town", key: true, lat: lat(20), lon: 85 };
    const arrival = waveArrival(RIVER, town, [WARNING]);
    if (arrival?.kind !== "expected") throw new Error("the town is on the river");

    const before = waveFront(RIVER, [WARNING], arrival.at - 30);
    expect(before!.head[0]).toBeGreaterThan(lat(20) + 0.001);
    expect(townsTheWaveReached(RIVER, [WARNING], [town], arrival.at - 1).size).toBe(0);

    const during = waveFront(RIVER, [WARNING], arrival.at);
    expect(during!.head[0]).toBeCloseTo(lat(20), 3);
    expect(townsTheWaveReached(RIVER, [WARNING], [town], arrival.at).get("Betrawati")).toBe(
      arrival.at,
    );
    // The stamp stays for the rest of the replay.
    expect(townsTheWaveReached(RIVER, [WARNING], [town], arrival.at + 9000).has("Betrawati")).toBe(
      true,
    );
  });

  it("does not stamp a town the river does not run by", () => {
    const farAway = { name: "Pokhara", kind: "city", key: true, lat: 28.2, lon: 84 };
    expect(townsTheWaveReached(RIVER, [WARNING], [farAway], SURGE_T + 100_000).size).toBe(0);
  });

  it("moves like the ETA when a measured speed is present", () => {
    const measured: FlashFloodWarning = {
      ...WARNING,
      measured: { node: "s1", km: 0, surge_t: SURGE_T + 190, speed_kmh: 30 },
    };
    const town = { lat: lat(20), lon: 85 };
    const arrival = waveArrival(RIVER, town, [measured]);
    if (arrival?.kind !== "expected") throw new Error("the town is on the river");
    // 20 km at the measured 30 km/h, from the second Node's Surge.
    expect(arrival.at).toBeCloseTo(SURGE_T + 190 + (20 / 30) * 3600, 0);
    expect(waveFront(RIVER, [measured], arrival.at)!.head[0]).toBeCloseTo(lat(20), 3);
  });
});

describe("the Nodes the wave front passed", () => {
  const nodes = [
    { id: "s2", riverKm: 10 },
    { id: "s0", riverKm: -10 },
    { id: "porch", riverKm: null },
  ];

  it("are wave-white from the moment of passing for two event minutes, then not", () => {
    expect(WAVE_FLASH_SECONDS).toBe(120);
    expect(nodesTheWavePassed(RIVER, [WARNING], nodes, TEN_KM_AT - 1)).toEqual([]);
    expect(nodesTheWavePassed(RIVER, [WARNING], nodes, TEN_KM_AT)).toEqual(["s2"]);
    expect(nodesTheWavePassed(RIVER, [WARNING], nodes, TEN_KM_AT + 119)).toEqual(["s2"]);
    expect(nodesTheWavePassed(RIVER, [WARNING], nodes, TEN_KM_AT + 120)).toEqual([]);
  });

  it("never include the origin Node or a Node off the river", () => {
    expect(nodesTheWavePassed(RIVER, [WARNING], nodes, SURGE_T + 60)).toEqual([]);
  });
});
