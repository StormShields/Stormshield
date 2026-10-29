import { ListChecks } from "lucide-react";
import { useState } from "react";

import type { Shelter } from "./evacuationPlan";
import { RegistryTab, type RegistrySummary } from "./RegistryTab";
import { ReplayControls } from "./ReplayControls";
import { WarningsTab, type WarningLog } from "./WarningsTab";
import type { EventClockFeed } from "./useEventClock";
import { usePolledJson } from "./usePolledJson";

const TABS = ["Registry", "Replay", "Warnings", "Shelters"] as const;
type Tab = (typeof TABS)[number];
const REGISTRY_POLL_MS = 1000;

type Props = {
  live: boolean;
  eventClock: EventClockFeed;
  shelters: Shelter[];
  openShelterIds: string[];
  onOpenShelterIdsChanged: (openIds: string[]) => void;
  onClose: () => void;
};

async function setShelterOpen(id: string, open: boolean): Promise<string[]> {
  const response = await fetch("/api/shelters/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, open }),
  });
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({ detail: undefined }));
    throw new Error(typeof detail === "string" ? detail : `Node API returned ${response.status}`);
  }
  return (await response.json()).open;
}

export function HubPanel({
  live,
  eventClock,
  shelters,
  openShelterIds,
  onOpenShelterIdsChanged,
  onClose,
}: Props) {
  const [changingShelterId, setChangingShelterId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Registry");
  // Polled whichever tab is showing, so the Registry badge counts Sign-ups as they arrive.
  const registry = usePolledJson<RegistrySummary>("/api/registry", REGISTRY_POLL_MS);
  const warningLog = usePolledJson<WarningLog>(
    tab === "Warnings" ? "/api/warnings" : null,
    REGISTRY_POLL_MS,
  );
  const waitingSignUps = registry?.nodes.filter((row) => row.status === "waiting").length ?? 0;

  const setStatus = async (shelter: Shelter, open: boolean) => {
    setChangingShelterId(shelter.id);
    setProblem(null);
    try {
      onOpenShelterIdsChanged(await setShelterOpen(shelter.id, open));
    } catch (error) {
      console.error(error);
      setProblem(
        `Could not ${open ? "open" : "close"} ${shelter.name}: ${(error as Error).message}`,
      );
    } finally {
      setChangingShelterId(null);
    }
  };

  return (
    <aside role="dialog" aria-label="Hub Panel" className="slide-over">
      <h2>Hub</h2>
      <div role="tablist" className="tabs">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
          >
            {name === "Registry" && <ListChecks size={16} aria-hidden="true" />}
            {name}
            {name === "Registry" && waitingSignUps > 0 && (
              <span className="tab-badge" aria-label={`${waitingSignUps} Sign-ups waiting`}>
                {waitingSignUps}
              </span>
            )}
          </button>
        ))}
      </div>
      {tab === "Registry" && <RegistryTab registry={registry} />}
      {tab === "Replay" &&
        (live ? (
          <section aria-label="Replay controls">
            <h3>Replay</h3>
            <p role="status">Live Sensors are reporting, so no Replay can play.</p>
          </section>
        ) : (
          <ReplayControls eventClock={eventClock} />
        ))}
      {tab === "Warnings" && <WarningsTab log={warningLog} registry={registry} />}
      {tab === "Shelters" && (
        <>
          {shelters.length === 0 && <p>No Shelters yet: this Hub has no Cache Pack.</p>}
          <ul className="shelter-list">
            {shelters.map((shelter) => {
              const open = openShelterIds.includes(shelter.id);
              return (
                <li key={shelter.id}>
                  <span>{shelter.name}</span>
                  <span className={`shelter-status ${open ? "open" : "closed"}`}>
                    {open ? "Open" : "Closed"}
                  </span>
                  <button
                    type="button"
                    disabled={changingShelterId !== null}
                    aria-label={`${open ? "Close" : "Open"} ${shelter.name}`}
                    onClick={() => setStatus(shelter, !open)}
                  >
                    {open ? "Close" : "Open"}
                  </button>
                </li>
              );
            })}
          </ul>
          {problem && <p role="alert">{problem}</p>}
        </>
      )}
      <div className="actions">
        <button type="button" onClick={onClose}>
          Close panel
        </button>
      </div>
    </aside>
  );
}
