import { useState } from "react";

import { EventClockTag } from "./EventClockTag";
import type { EventClockFeed } from "./useEventClock";
import { usePolledJson } from "./usePolledJson";

type ReplayEvents = { events: { id: string; label: string; real: boolean }[] };
type Phase = { id: string; label: string; event_t: number };
type ReplayPhases = { phases: Phase[]; internet_cue_event_t: number };

// Matches the Hub's ReplayRate: slower than x5 and S0's rise no longer counts as a Surge.
const REPLAY_RATES = [5, 10, 30];
const DEFAULT_REPLAY_RATE = 30;

async function sendToReplay(action: string, body?: object): Promise<void> {
  const response = await fetch(`/api/replay/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({ detail: undefined }));
    throw new Error(typeof detail === "string" ? detail : `Node API returned ${response.status}`);
  }
}

// The Replay section of the Hub Panel and the Sandbox Panel. The Event clock it shows arrives by
// the header's poll, so a press shows up within a second.
export function ReplayControls({ eventClock }: { eventClock: EventClockFeed }) {
  const { clock, heard } = eventClock;
  const replayEvents = usePolledJson<ReplayEvents>("/api/replay/events");
  const [problem, setProblem] = useState<string | null>(null);
  // Picked before Start; a running replay shows the Event the Event clock carries.
  const [pickedEventId, setPickedEventId] = useState<string | null>(null);
  const shownEventId = clock?.event ?? pickedEventId ?? replayEvents?.events[0]?.id;
  const replayPhases = usePolledJson<ReplayPhases>(
    shownEventId === undefined
      ? "/api/replay/phases"
      : `/api/replay/phases?event=${encodeURIComponent(shownEventId)}`,
  );
  // Picked before Start; a running replay shows the rate the Event clock carries.
  const [pickedRate, setPickedRate] = useState<number | null>(null);

  // Until the clock is heard, a Start button would suggest no replay is running when one may be.
  if (!heard) {
    return (
      <section aria-label="Replay controls">
        <h3>Replay</h3>
        <p role="status">Waiting for the Hub to answer</p>
      </section>
    );
  }

  const send = async (action: string, body?: object) => {
    setProblem(null);
    try {
      if (action === "start" && pickedRate !== null)
        await sendToReplay("rate", { rate: pickedRate });
      // A stopped clock names no Event, so the controls that act on one carry the picked Event.
      const needsEvent = ["start", "reset", "jump"].includes(action) && clock === null;
      await sendToReplay(
        action,
        needsEvent && shownEventId ? { ...body, event: shownEventId } : body,
      );
    } catch (error) {
      console.error(error);
      setProblem(`Could not ${action} the replay: ${(error as Error).message}`);
    }
  };

  const currentPhase = clock
    ? replayPhases?.phases.filter((phase) => phase.event_t <= clock.event_t).at(-1)
    : undefined;
  const internetCueReached =
    clock !== null && replayPhases !== null && clock.event_t >= replayPhases.internet_cue_event_t;

  const shownRate = clock?.rate ?? pickedRate ?? DEFAULT_REPLAY_RATE;

  return (
    <section aria-label="Replay controls">
      <h3>Replay</h3>
      {/* Every Event is a Replay, never a live flood, even before the clock tag appears. */}
      <p className="replay-label">REPLAY</p>
      {replayEvents && (
        <label className="event-picker">
          Event
          <select
            value={shownEventId}
            onChange={(change) => {
              if (clock === null) setPickedEventId(change.target.value);
              else send("start", { event: change.target.value });
            }}
          >
            {replayEvents.events.map((event) => (
              <option key={event.id} value={event.id}>
                {event.real ? event.label : `${event.label} (made up)`}
              </option>
            ))}
          </select>
        </label>
      )}
      <EventClockTag clock={clock} />
      <div className="actions" role="group" aria-label="Replay speed">
        {REPLAY_RATES.map((rate) => (
          <button
            key={rate}
            type="button"
            aria-pressed={rate === shownRate}
            onClick={() => {
              if (clock === null) setPickedRate(rate);
              else send("rate", { rate });
            }}
          >
            ×{rate}
          </button>
        ))}
      </div>
      {internetCueReached && (
        <p role="status" className="internet-cue">
          Cut the internet now
        </p>
      )}
      <div className="actions">
        {clock === null && (
          <button type="button" onClick={() => send("start")}>
            Start
          </button>
        )}
        {clock?.state === "playing" && (
          <button type="button" onClick={() => send("pause")}>
            Pause
          </button>
        )}
        {clock?.state === "paused" && (
          <button type="button" onClick={() => send("resume")}>
            Resume
          </button>
        )}
        <button type="button" onClick={() => send("reset")}>
          Reset
        </button>
      </div>
      <ul className="phase-list">
        {replayPhases?.phases.map((phase) => (
          <li key={phase.id}>
            <button
              type="button"
              aria-current={phase.id === currentPhase?.id ? "step" : undefined}
              onClick={() => send("jump", { phase: phase.id })}
            >
              {phase.label}
            </button>
          </li>
        ))}
      </ul>
      {problem && <p role="alert">{problem}</p>}
    </section>
  );
}
