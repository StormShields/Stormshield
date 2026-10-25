import { Check, TriangleAlert } from "lucide-react";

import { communityKey, officialKey } from "./acknowledgedWarnings";

import {
  issuedInRegion,
  issuedUnix,
  leadTimeLine,
  officialTag,
  sourceName,
  type OfficialAlert,
} from "./officialAlerts";
import {
  communityWarningTitle,
  measuredSpeedLine,
  OFFICIAL_SOURCE,
  warningSentence,
  type CommunityWarning,
} from "./communityWarnings";
import type { NodeSnapshot, Region } from "./nodeState";
import { Panel, type PanelControl } from "./Panel";
import type { WaveArrival } from "./waveEta";
import { WaveEtaLine } from "./WaveEtaLine";

// The only place a desktop resident acknowledges a warning (D-27).
function AcknowledgeControl({ done, onAcknowledge }: { done: boolean; onAcknowledge: () => void }) {
  return done ? (
    <p className="acknowledged">
      <Check size={14} aria-hidden="true" /> Acknowledged
    </p>
  ) : (
    <button type="button" className="acknowledge" onClick={onAcknowledge}>
      Acknowledge
    </button>
  );
}

export function AlertsPanel({
  alerts,
  region,
  warnings,
  nodes,
  thisNodeId,
  appliesToYouIds,
  firstCommunityWarningAt,
  waveArrival,
  eventT,
  online,
  acknowledged,
  onAcknowledge,
  panel,
}: {
  alerts: OfficialAlert[];
  region: Region | null;
  warnings: CommunityWarning[];
  nodes: NodeSnapshot[];
  thisNodeId: string;
  appliesToYouIds: string[];
  firstCommunityWarningAt: number | null;
  waveArrival: WaveArrival | null;
  eventT: number | null;
  online: boolean;
  acknowledged: string[];
  onAcknowledge: (key: string) => void;
  panel: PanelControl;
}) {
  const units = region?.display_units ?? null;
  const leadTime = leadTimeLine(firstCommunityWarningAt, alerts, region?.time_zone ?? null);
  const newestFirst = [...alerts].sort((a, b) => issuedUnix(b) - issuedUnix(a));
  return (
    <Panel label="Alerts" {...panel}>
      {leadTime && <p className="lead-time">{leadTime}</p>}
      {newestFirst.length === 0 && warnings.length === 0 && (
        <div className="empty-panel">
          <span className="empty-panel-icon">
            <TriangleAlert size={20} aria-hidden="true" />
          </span>
          <p>No Official Alerts or Community Warnings right now.</p>
        </div>
      )}
      {newestFirst.map((alert) => (
        <article key={alert.id} className="official-alert" aria-label="Official Alert">
          <p className="official-alert-tags">
            <span className="official-tag">{officialTag(alert)}</span>
            <span>{sourceName(region, alert)}</span>
            {appliesToYouIds.includes(alert.id) && (
              <span className="applies-chip">APPLIES TO YOUR HOUSEHOLD</span>
            )}
          </p>
          <h3>{alert.headline}</h3>
          <p className="official-alert-issued">
            Issued {issuedInRegion(alert, region?.time_zone ?? null)}
          </p>
          {online ? (
            <a href={alert.url} target="_blank" rel="noreferrer">
              Read at the source
            </a>
          ) : (
            <p className="official-alert-offline">Source link opens when online</p>
          )}
          <AcknowledgeControl
            done={acknowledged.includes(officialKey(alert))}
            onAcknowledge={() => onAcknowledge(officialKey(alert))}
          />
        </article>
      ))}
      {[...warnings].reverse().map((warning) => {
        const measuredLine = measuredSpeedLine(
          warning,
          (id) => nodes.find((node) => node.id === id)?.name ?? id,
          units,
        );
        return (
          <article key={warning.id} className="community-warning" aria-label="Community Warning">
            <WaveEtaLine arrival={waveArrival} eventT={eventT} />
            <p className="community-warning-tag">{communityWarningTitle(warning)}</p>
            <h3>{warningSentence(warning, nodes, thisNodeId, units)}</h3>
            {measuredLine && <p className="measured-speed">{measuredLine}</p>}
            <p>Signed by the Hub · verified</p>
            <p>Check official sources for any evacuation decision.</p>
            {online ? (
              <a href={OFFICIAL_SOURCE.url} target="_blank" rel="noreferrer">
                Official source: {OFFICIAL_SOURCE.name}
              </a>
            ) : (
              <p>Official source link opens when online</p>
            )}
            <AcknowledgeControl
              done={acknowledged.includes(communityKey(warning))}
              onAcknowledge={() => onAcknowledge(communityKey(warning))}
            />
          </article>
        );
      })}
    </Panel>
  );
}
