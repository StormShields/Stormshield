import type { TakeoverWarning } from "./acknowledgedWarnings";
import { useChimeForWarning } from "./chime";
import { communityWarningTitle, warningSentence } from "./communityWarnings";
import type { NodeSnapshot } from "./nodeState";
import { officialTag } from "./officialAlerts";
import { useRegion } from "./RegionContext";

// The desktop's answer to a new warning (D-22, D-27): a band under the top bar that leaves the map
// undimmed. It has no button; the warning's card in the Alerts Panel is acknowledged instead.
export function WarningBand({
  pending,
  nodes,
  thisNodeId,
}: {
  pending: TakeoverWarning[];
  nodes: NodeSnapshot[];
  thisNodeId: string;
}) {
  const region = useRegion();
  const current = pending[0];
  useChimeForWarning(current?.key);
  if (!current) return null;
  const tag =
    current.kind === "official"
      ? officialTag(current.alert)
      : communityWarningTitle(current.warning);
  const sentence =
    current.kind === "official"
      ? current.alert.headline
      : warningSentence(current.warning, nodes, thisNodeId, region?.display_units ?? null);
  return (
    // The key restarts the border pulse for each warning.
    <div
      key={current.key}
      role="alert"
      aria-label="Warning"
      className={`warning-band ${current.kind}`}
    >
      <p className="warning-band-tag">
        {tag}
        {pending.length > 1 && <span className="warning-band-count">1 of {pending.length}</span>}
      </p>
      <p className="warning-band-sentence">{sentence}</p>
      <p>Check official sources for any evacuation decision.</p>
    </div>
  );
}

// Beside the Flood Risk chip once a warning is acknowledged (D-29); it reopens the warning's card.
export function WarningChip({
  minutesLeft,
  community,
  onOpen,
}: {
  minutesLeft: number | null;
  community: boolean;
  onOpen: () => void;
}) {
  const label = community ? "WARNING" : "OFFICIAL ALERT";
  return (
    <button
      type="button"
      className={`warning-chip ${community ? "community" : "official"}`}
      onClick={onOpen}
    >
      {minutesLeft === null ? label : `${label} · ${minutesLeft} MIN`}
    </button>
  );
}
