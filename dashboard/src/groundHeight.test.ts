import { groundHeightCm, tilePosition, type ElevationTile } from "./groundHeight";

// A 2 x 2 tile whose pixels are 1, 2, 3 and 4 m: Terrarium stores 32768 + height in red and green.
function tileOfMetres(metres: number[]): ElevationTile {
  const data = new Uint8ClampedArray(
    metres.flatMap((height) => {
      const stored = 32768 + height;
      return [Math.floor(stored / 256), Math.floor(stored % 256), 0, 255];
    }),
  );
  return { width: 2, height: 2, data };
}

const HOME = { lat: 26.45, lon: -81.95 };

describe("a home's ground height from the pack's terrain", () => {
  it("places a point on the tile grid", () => {
    expect(tilePosition({ lat: 0, lon: 0 }, 1)).toEqual({ x: 1, y: 1 });
    expect(tilePosition({ lat: 0, lon: -180 }, 2).x).toBe(0);
  });

  it("reads the pixel the home falls in, in centimetres", async () => {
    const { x, y } = tilePosition(HOME, 12);
    const pixel = Math.floor((y % 1) * 2) * 2 + Math.floor((x % 1) * 2);
    const tile = tileOfMetres([1, 2, 3, 4]);
    const loadTile = vi.fn().mockResolvedValue(tile);
    expect(await groundHeightCm(HOME, [9, 12], loadTile)).toBe((pixel + 1) * 100);
    expect(loadTile).toHaveBeenCalledWith(12, Math.floor(x), Math.floor(y));
  });

  it("falls back to a coarser zoom when the pack lacks the finest tile", async () => {
    const loadTile = vi.fn(async (zoom: number) =>
      zoom === 10 ? tileOfMetres([5, 5, 5, 5]) : null,
    );
    expect(await groundHeightCm(HOME, [9, 12], loadTile)).toBe(500);
    expect(loadTile.mock.calls.map(([zoom]) => zoom)).toEqual([12, 11, 10]);
  });

  it("is null when no tile covers the home", async () => {
    expect(await groundHeightCm(HOME, [9, 12], async () => null)).toBeNull();
  });
});
