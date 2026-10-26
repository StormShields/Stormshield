import { useEffect, useState } from "react";

import type { Home } from "./householdProfile";
import { terrariumHeight } from "./heightBands";

export type ElevationTile = { width: number; height: number; data: Uint8ClampedArray };

// Where a point falls on the Web Mercator tile grid of one zoom: the integer part is the tile, the
// rest is the place inside it.
export function tilePosition({ lat, lon }: Home, zoom: number): { x: number; y: number } {
  const tiles = 2 ** zoom;
  return {
    x: ((lon + 180) / 360) * tiles,
    y: ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * tiles,
  };
}

// The home's ground height in centimetres above the terrain's datum, from the finest elevation
// tile the pack holds for it; null when the pack has none. `loadTile` answers null for a tile the
// pack lacks. The home is read here on the device and never sent anywhere.
export async function groundHeightCm(
  home: Home,
  [lowestZoom, highestZoom]: [number, number],
  loadTile: (zoom: number, x: number, y: number) => Promise<ElevationTile | null>,
): Promise<number | null> {
  for (let zoom = highestZoom; zoom >= lowestZoom; zoom--) {
    const { x, y } = tilePosition(home, zoom);
    const tile = await loadTile(zoom, Math.floor(x), Math.floor(y));
    if (tile === null) continue;
    const column = Math.floor((x % 1) * tile.width);
    const row = Math.floor((y % 1) * tile.height);
    const at = (row * tile.width + column) * 4;
    return terrariumHeight(tile.data[at], tile.data[at + 1], tile.data[at + 2]) * 100;
  }
  return null;
}

export async function loadElevationTile(
  zoom: number,
  x: number,
  y: number,
): Promise<ElevationTile | null> {
  const response = await fetch(`/api/cache-pack/files/elevation/${zoom}/${x}/${y}.png`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Node API returned ${response.status} for an elevation tile`);
  const bitmap = await createImageBitmap(await response.blob());
  const context = new OffscreenCanvas(bitmap.width, bitmap.height).getContext("2d")!;
  context.drawImage(bitmap, 0, 0);
  const { width, height, data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
  return { width, height, data };
}

// The home's ground height, or null while it is being read, or when `zooms` is null (the pack has
// no terrain) or no tile covers the home.
export function useGroundHeightCm(
  home: Home | null,
  zooms: [number, number] | null,
): number | null {
  const [found, setFound] = useState<{ key: string; cm: number | null } | null>(null);
  const key = home && zooms ? `${home.lat},${home.lon},${zooms[0]},${zooms[1]}` : null;
  useEffect(() => {
    if (!home || !zooms || key === null) return;
    let cancelled = false;
    groundHeightCm(home, zooms, loadElevationTile)
      .then((cm) => {
        if (!cancelled) setFound({ key, cm });
      })
      .catch((error) => console.error(error));
    return () => {
      cancelled = true;
    };
    // `key` stands for the home and the zooms, which are new objects on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return found !== null && found.key === key ? found.cm : null;
}
