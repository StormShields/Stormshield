import { Fragment } from "react";

import { CameraLine } from "./CameraLine";
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
  air_temperature: "Air temperature",
  camera: "Camera",
  humidity: "Humidity",
  rain_rate: "Rain rate",
  water_level: "Water level",
  soil_moisture: "Soil moisture",
  wind_speed: "Wind speed",
};

const SNAKE_CASE_NAME = /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/;

// A kind the dashboard has no label for reads as its own name: "soil_temperature" is "Soil
// temperature", and a name that isn't plain snake_case is shown exactly as sent. A kind is data,
// so "constructor" and "__proto__" must not find anything on Object.prototype.
export function kindLabel(kind: ReadingKind): string {
  if (Object.hasOwn(KIND_LABELS, kind)) return KIND_LABELS[kind] as string;
  if (!SNAKE_CASE_NAME.test(kind)) return kind;
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
  // True in the Sandbox, whose Hub passes on every Sensor's Camera picture.
  inSandbox: boolean;
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
  inSandbox,
}: Props) {
  const reducedMotion = usePrefersReducedMotion();

  const { pinned, rungs, offRiver } = readingsLadder(nodes, hubId);
  const firstNotCountedId = offRiver.find((node) => !node.registered && !node.isThisNode)?.id;
  const waveAfter = rungBeforeWave(rungs, waveKm);

  // A picture never crosses the Mesh: the Sandbox's Hub has them all, anywhere else this page can
  // reach only the Camera of the Node it is connected to.
  const pictureUrlOf = (node: NodeOnMap) =>
    inSandbox
      ? `/api/sandbox/sensors/${encodeURIComponent(node.id)}/picture`
      : node.isThisNode
        ? "/api/camera/picture"
        : null;

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
              {measurement.kind === "camera" ? (
                <CameraLine
                  pictureNumber={measurement.value}
                  shown={measurement.shown}
                  pictureUrl={pictureUrlOf(node)}
                />
              ) : (
                <ReadingSlot
                  value={measurement.value}
                  trend={trends[historyKey(node.id, measurement.kind)]}
                >
                  {kindLabel(measurement.kind)}: {measurement.shown}
                </ReadingSlot>
              )}
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
