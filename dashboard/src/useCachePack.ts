import { useEffect, useRef, useState } from "react";

import type { Basemap, CachePackContents, HighGroundPoint } from "./evacuationPlan";
import type { RouteGrid } from "./routeGrid";

const RETRY_EVERY_MS = 5000;

type Manifest = {
  built?: string;
  route_grid?: RouteGrid;
  bbox?: Basemap["bbox"];
  terrain?: { approximate: boolean; zooms: [number, number] };
  sources?: Basemap["credits"][number][];
  files?: Record<string, string>;
};

async function getJson(url: string): Promise<unknown> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Node API returned ${response.status} for ${url}`);
  return response.json();
}

// A pack built before the basemap has no `basemap/` files, and the map then draws without them.
function basemapOf(manifest: Manifest | null | undefined): Basemap | null {
  if (!manifest?.bbox || !manifest.terrain) return null;
  const hasBasemap = Object.keys(manifest.files ?? {}).some((path) => path.startsWith("basemap/"));
  if (!hasBasemap) return null;
  return { bbox: manifest.bbox, terrain: manifest.terrain, credits: manifest.sources ?? [] };
}

async function fetchCachePack(): Promise<CachePackContents | null> {
  const status = (await getJson("/api/cache-pack")) as {
    available?: boolean;
    manifest?: Manifest | null;
  };
  if (status.available !== true) return null;
  const [shelters, floodProne] = await Promise.all([
    getJson("/api/cache-pack/files/shelters.json"),
    getJson("/api/cache-pack/files/flood_prone.geojson"),
  ]);
  // A pack built before High-ground points lacks the file; asking for it would only log a 404.
  const highGround: HighGroundPoint[] = status.manifest?.files?.["high_ground.json"]
    ? ((await getJson("/api/cache-pack/files/high_ground.json")) as HighGroundPoint[])
    : [];
  // A pack built without Routes has no grid.
  const routeGrid = status.manifest?.route_grid ?? null;
  const bbox = status.manifest?.bbox ?? null;
  const built = status.manifest?.built ?? null;
  const basemap = basemapOf(status.manifest);
  return { shelters, highGround, floodProne, routeGrid, bbox, built, basemap } as CachePackContents;
}

// The pack never changes once a Node holds a valid one, so it is read once and then kept, until
// the Sandbox switches Region: the Hub then holds another pack, which is read afresh.
export function useCachePack(regionName: string | null): CachePackContents | null {
  const [pack, setPack] = useState<CachePackContents | null>(null);
  const [generation, setGeneration] = useState(0);
  const packOf = useRef<string | null>(null);
  useEffect(() => {
    if (regionName === null) return;
    if (packOf.current !== null && packOf.current !== regionName) {
      setPack(null);
      setGeneration((count) => count + 1);
    }
    packOf.current = regionName;
  }, [regionName]);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const retryLater = () => {
      if (!cancelled) timer = setTimeout(load, RETRY_EVERY_MS);
    };
    const load = () =>
      fetchCachePack()
        .then((loaded) => {
          if (cancelled) return;
          if (loaded) setPack(loaded);
          else retryLater();
        })
        .catch((error) => {
          console.error(error);
          retryLater();
        });
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [generation]);
  return pack;
}
