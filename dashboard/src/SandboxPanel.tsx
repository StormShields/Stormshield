import { distanceInDisplayUnit } from "./displayUnits";
import { Panel, type PanelControl } from "./Panel";
import { useRegion } from "./RegionContext";
import { kindLabel } from "./ReadingsPanel";
import { ReplayControls } from "./ReplayControls";
import type { EventClockFeed } from "./useEventClock";
import type { SandboxNode, SandboxNodes, SandboxRegions } from "./useSandboxNodes";

const MIN_RANGE_KM = 0.1;
const MAX_RANGE_KM = 50;
const RANGE_STEP_KM = 0.1;

type Props = {
  sandbox: SandboxNodes;
  regions: SandboxRegions | null;
  onSwitchRegion: (name: string) => Promise<void>;
  // Present only in the app, the one Sandbox a Stop button can end.
  onStop: (() => void) | null;
  problem: string | null;
  onSetRadioRange: (metres: number) => Promise<void>;
  // "Add Sensor" arms the map: the next tap places a Sensor. Pressing it again disarms.
  placing: boolean;
  onTogglePlacing: () => void;
  onRemoveSensor: (id: string) => Promise<void>;
  onSetSensorKinds: (id: string, position: [number, number], kinds: string[]) => Promise<void>;
  // Whether the Hub has sent any Community Warning yet; until it has, nobody has heard one.
  warningSent: boolean;
  eventClock: EventClockFeed;
  panel: PanelControl;
};

function hopsText(node: SandboxNode): string {
  if (node.role === "hub") return "Hub";
  if (node.hops === null) return "no path to Hub";
  return node.hops === 1 ? "1 hop to Hub" : `${node.hops} hops to Hub`;
}

function warningText(node: SandboxNode, warningSent: boolean): string {
  if (!warningSent) return "no warning yet";
  return node.heard_warning ? "heard the warning" : "has not heard the warning";
}

export function SandboxPanel({
  sandbox,
  regions,
  onSwitchRegion,
  onStop,
  problem,
  onSetRadioRange,
  placing,
  onTogglePlacing,
  onRemoveSensor,
  onSetSensorKinds,
  warningSent,
  eventClock,
  panel,
}: Props) {
  const region = useRegion();
  const rangeKm = sandbox.radio_range_m / 1000;

  return (
    <Panel label="Sandbox" {...panel}>
      <p className="sandbox-label">SIMULATED</p>
      {regions && (
        <label className="sandbox-region">
          Region
          <select
            value={regions.current}
            onChange={(event) => void onSwitchRegion(event.target.value)}
          >
            {regions.regions.map(({ name, label }) => (
              <option key={name} value={name}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="sandbox-range">
        Radio range
        <input
          type="range"
          aria-label="Radio range"
          min={MIN_RANGE_KM}
          max={MAX_RANGE_KM}
          step={RANGE_STEP_KM}
          value={rangeKm}
          onChange={(event) => void onSetRadioRange(Math.round(Number(event.target.value) * 1000))}
        />
        <output>{distanceInDisplayUnit(rangeKm, region?.display_units ?? null)}</output>
      </label>
      <button
        type="button"
        className="sandbox-add"
        aria-pressed={placing}
        onClick={onTogglePlacing}
      >
        Add Sensor
      </button>
      {onStop && (
        <button type="button" className="sandbox-stop" onClick={onStop}>
          Stop Sandbox
        </button>
      )}
      {problem && <p role="alert">{problem}</p>}
      <ReplayControls eventClock={eventClock} />
      <ul aria-label="Sandbox Nodes" className="sandbox-nodes">
        {sandbox.nodes.map((node) => (
          <li key={node.id} className={node.hops === null ? "no-path" : undefined}>
            <strong>{node.name}</strong>
            <span>{hopsText(node)}</span>
            <span>{warningText(node, warningSent)}</span>
            {node.role === "sensor" && (
              <button
                type="button"
                aria-label={`Remove ${node.name}`}
                onClick={() => void onRemoveSensor(node.id)}
              >
                Remove
              </button>
            )}
            {node.role === "sensor" && (
              <fieldset className="sandbox-kinds">
                <legend>Kinds {node.name} measures</legend>
                {sandbox.offered_kinds.map((kind) => (
                  <label key={kind}>
                    <input
                      type="checkbox"
                      checked={node.kinds.includes(kind)}
                      onChange={(event) =>
                        void onSetSensorKinds(
                          node.id,
                          node.position,
                          sandbox.offered_kinds.filter((offered) =>
                            offered === kind ? event.target.checked : node.kinds.includes(offered),
                          ),
                        )
                      }
                    />
                    {kindLabel(kind)}
                  </label>
                ))}
              </fieldset>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
