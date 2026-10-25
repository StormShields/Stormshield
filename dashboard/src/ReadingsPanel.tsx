import { Fragment } from "react";

import { FloodRiskCard } from "./FloodRiskPanel";
import { NodeTags } from "./NodeTags";
import { Panel, type PanelControl } from "./Panel";
import type { NodeOnMap } from "./nodesOnMap";
import { ReadingSlot } from "./ReadingSlot";
import { readingsLadder, rungBeforeWave } from "./readingsLadder";
import { historyKey, type Trend } from "./readingTrends";
import type { FloodRisk, Hazard, ReadingKind, Region } from "./nodeState";
import { usePrefersReducedMotion } from "./useViewport";

const KIND_LABELS: Partial<Record<ReadingKind, string>> = {
  air_pressure: "Pressure",
  rain_rate: "Rain rate",
  water_level: "Water level",
  soil_moisture: "Soil moisture",
};

// A kind the dashboard has no label for reads as its own name: "wind_speed" is "Wind speed".
export function kindLabel(kind: ReadingKind): string {
  if (KIND_LABELS[kind]) return KIND_LABELS[kind];
  const words = kind.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

type Props = {
  nodes: NodeOnMap[];
  floodRisk: FloodRisk | null;
  region: Region | null;
  hazard: Hazard | null;
  // The Hub's id when this Node is the Hub; the Pi's card is the real Node that is not it.
  hubId: string | null;
  // River km of the wave front now, or null while no wave is running.
  waveKm: number | null;
  selectedId: string | null;
  // How often each Node's Flood Risk has risen; a new count flashes that Node's card once.
  rises: Record<string, number>;
  // The arrow of each reading, from the last 30 s of polls (`historyKey`).
  trends: Record<string, Trend>;
  onSelect: (id: string) => void;
  panel: PanelControl;
};

export function ReadingsPanel({
  nodes,
  floodRisk,
  region,
  hazard,
  hubId,
  waveKm,
  selectedId,
  rises,
  trends,
  onSelect,
  panel,
}: Props) {
  const reducedMotion = usePrefersReducedMotion();

  const { pinned, rungs, offRiver } = readingsLadder(nodes, hubId);
  const firstNotCountedId = offRiver.find((node) => !node.registered && !node.isThisNode)?.id;
  const waveAfter = rungBeforeWave(rungs, waveKm);

  const card = (
    node: NodeOnMap,
    { hero, liveSensors }: { hero: boolean; liveSensors?: boolean },
  ) => (
    <section
      aria-label={`Node ${node.label}`}
      aria-current={node.id === selectedId}
      className={[
        "node-card",
        node.stale && "stale",
        !node.registered && "unverified",
        !reducedMotion && "enters",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => onSelect(node.id)}
    >
      {(rises[node.id] ?? 0) > 0 && !reducedMotion && (
        <span key={rises[node.id]} className="card-flash" />
      )}
      <h3>
        {/* Clicks reach the card; the button only makes the card reachable by keyboard. */}
        <button>{node.label}</button>
        {liveSensors && <span className="tag live-sensors">LIVE SENSORS</span>}
        <NodeTags node={node} />
      </h3>
      {hero && node.waterLevelCm !== null && (
        <p className="hero-level">
          <ReadingSlot
            value={node.waterLevelCm}
            trend={trends[historyKey(node.id, "water_level")]}
            className={node.stale ? "water-level struck" : undefined}
          >
            {node.waterLevelShown}
          </ReadingSlot>
        </p>
      )}
      <ul className="reading-row">
        {node.measurements
          .filter((measurement) => !(hero && measurement.kind === "water_level"))
          .map((measurement) => (
            <li key={measurement.kind}>
              <ReadingSlot
                value={measurement.value}
                trend={trends[historyKey(node.id, measurement.kind)]}
              >
                {kindLabel(measurement.kind)}: {measurement.shown}
              </ReadingSlot>
            </li>
          ))}
        {/* On a coast a simulated Sensor whose ground is above the water sends no level, not zero;
            a real one without a level may simply have no water gauge. */}
        {region?.water_type === "coast" &&
          node.simulated &&
          node.measurements.length > 0 &&
          node.waterLevelCm === null && <li className="dry">{kindLabel("water_level")}: dry</li>}
      </ul>
    </section>
  );

  return (
    <Panel label="Readings" {...panel}>
      <FloodRiskCard floodRisk={floodRisk} region={region} hazard={hazard} />
      {pinned && card(pinned, { hero: false, liveSensors: true })}
      {rungs.length > 0 && (
        <ol className="river-ladder" aria-label="Valley Nodes by River km">
          {rungs.map((node, at) => (
            <Fragment key={node.id}>
              <li className="rung">
                <span className="rung-km">km {node.riverKm}</span>
                {card(node, { hero: true })}
              </li>
              {waveAfter === at && (
                <li className="wave-front">Wave front · km {Math.round(waveKm as number)}</li>
              )}
            </Fragment>
          ))}
        </ol>
      )}
      {offRiver.map((node) => (
        <Fragment key={node.id}>
          {node.id === firstNotCountedId && <p className="not-counted-divider">Not counted</p>}
          {card(node, { hero: false })}
        </Fragment>
      ))}
    </Panel>
  );
}
