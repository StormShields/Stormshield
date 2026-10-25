import { TriangleAlert } from "lucide-react";

import {
  measuredSpeedLine,
  reasonsSentence,
  riverKm,
  stormSurgeLevel,
  type CommunityWarning,
} from "./communityWarnings";
import { useRegion } from "./RegionContext";
import { regionClockTime } from "./regionTime";
import type { RegistrySummary } from "./RegistryTab";

// The answer of the Hub's GET /api/warnings: everything it sent since it started, newest first.
export type WarningLog = { warnings: CommunityWarning[] };

export function WarningsTab({
  log,
  registry,
}: {
  log: WarningLog | null;
  registry: RegistrySummary | null;
}) {
  const region = useRegion();
  if (!log) return <p>Loading the warning log…</p>;
  if (log.warnings.length === 0) {
    return (
      <div className="empty-panel">
        <span className="empty-panel-icon">
          <TriangleAlert size={20} aria-hidden="true" />
        </span>
        <p>
          No Community Warning sent yet. One goes out when a Registered Node{" "}
          {region?.water_type === "coast"
            ? "reports water past the warning height and rising"
            : "reports a sudden rise in the river"}
          .
        </p>
      </div>
    );
  }
  return (
    <section aria-label="Warning log">
      <ul className="registry-list">
        {log.warnings.map((warning) => {
          const nameOf = (id: string) => registry?.nodes.find((row) => row.id === id)?.name ?? id;
          const name = nameOf(warning.origin);
          const units = region?.display_units ?? null;
          const measuredLine = measuredSpeedLine(warning, nameOf, units);
          return (
            <li key={warning.id}>
              <strong>{region && regionClockTime(warning.surge_t, region.time_zone)}</strong>
              <span>{name}</span>
              {warning.hazard === "storm_surge" ? (
                <span>Water is {stormSurgeLevel(warning, units)}</span>
              ) : (
                <>
                  <span>{riverKm(warning.origin_km)}</span>
                  <span>{reasonsSentence(warning)}</span>
                </>
              )}
              {measuredLine && <span>{measuredLine}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
