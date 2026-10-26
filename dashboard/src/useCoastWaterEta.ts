import { useState } from "react";

import { coastWaterEta, type CoastWaterEta, type LevelSample } from "./coastWaterEta";
import type { Home } from "./householdProfile";
import type { NodeOnMap } from "./nodesOnMap";
import type { Region } from "./nodeState";

export type LevelHistory = Record<string, LevelSample[]>;

// A level is kept when it changes, with the Event time it was heard at. Samples older than the one
// just before the rising window are dropped, and a clock that went back (a Replay reset) starts
// over. Returns `history` itself when nothing changed, so a poll that brings nothing new re-renders
// nothing.
export function rememberLevels(
  history: LevelHistory,
  nodes: NodeOnMap[],
  eventT: number | null,
  windowS: number,
): LevelHistory {
  if (eventT === null) return history;
  let next = history;
  for (const { id, waterLevelCm } of nodes) {
    if (waterLevelCm === null) continue;
    const kept = (history[id] ?? []).filter((sample) => sample.t <= eventT);
    if (kept.at(-1)?.levelCm === waterLevelCm) {
      if (kept.length !== (history[id] ?? []).length) next = { ...next, [id]: kept };
      continue;
    }
    const samples = [...kept, { t: eventT, levelCm: waterLevelCm }];
    const baseline = samples.filter((sample) => sample.t <= eventT - windowS).at(-1);
    next = { ...next, [id]: baseline ? samples.slice(samples.indexOf(baseline)) : samples };
  }
  return next;
}

// The Registered Node closest to home that is heard from and reports a water level.
export function nearestLevelNode(nodes: NodeOnMap[], home: Home): NodeOnMap | null {
  const distance = ({ position }: NodeOnMap) =>
    (position[0] - home.lat) ** 2 + (position[1] - home.lon) ** 2;
  const reporting = nodes.filter(
    (node) => node.registered && !node.stale && node.waterLevelCm !== null,
  );
  return reporting.sort((a, b) => distance(a) - distance(b))[0] ?? null;
}

// This resident's Water ETA on a coast, worked out here on the device from the home's ground
// height and the nearest Node's level; null on a river, and whenever there is none to give.
export function useCoastWaterEta({
  region,
  home,
  groundCm,
  nodes,
  eventT,
}: {
  region: Region | null;
  home: Home | null;
  groundCm: number | null;
  nodes: NodeOnMap[];
  eventT: number | null;
}): CoastWaterEta | null {
  const [seen, setSeen] = useState<LevelHistory>({});
  const surge = region?.water_type === "coast" ? region.storm_surge : null;
  const history = rememberLevels(seen, nodes, eventT, surge?.rising_window_s ?? 0);
  if (history !== seen) setSeen(history);
  if (!surge || !home || groundCm === null || eventT === null) return null;
  const node = nearestLevelNode(nodes, home);
  return node ? coastWaterEta(groundCm, history[node.id] ?? [], surge, eventT) : null;
}
