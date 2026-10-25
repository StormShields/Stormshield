# A Region runs live or on its own Replay

**Status:** ready-for-agent

From issue #89 (grilled 25 Oct 2026), under #26. Words follow `CONTEXT.md`, which this spec adds **Live Hub** to; the Replay entry already says "a Region runs either on live readings or on one of its own Replays, never both on one map, and never another Region's Replay". Builds on `docs/specs/regions-events-and-sandbox.md` (Events, the Event picker of #76) and `docs/specs/readings-on-the-map.md`.

## Problem Statement

Any Hub can pick and play an Event from the Hub Panel. Nothing stops a Hub whose Region has real Sensors reporting from starting a Replay over them. The map then shows real Community Readings next to Simulated Readings, the Flood Risk and the Hazard trigger read both, and a Replay can raise a Community Warning (and email the team) in a neighbourhood whose real water is calm. A resident cannot tell from a screenshot which readings are real, and the one rule the project never bends is that a Replay never passes for a live flood.

Today every Sensor reads its Simulated Readings from the Replay surface, and it keeps sending the first moment of its first Event even while the Event clock is stopped. Once a Sensor has real hardware, the same map would carry live and simulated Nodes side by side with nothing choosing between them.

There is a second, quieter gap. Every Node, the Hub included, takes any Event clock it hears over the Mesh, even one naming an Event it does not hold. A Hub of another Region on the same Mesh (two demos in one room, a neighbouring network in radio range) could start, pause or move this Hub's clock, and every Node would read its own Region's first Event at the foreign clock's time.

## Solution

Live readings win. A Hub is a **Live Hub** while it is hearing a Community Reading that is not a Simulated Reading, from a Registered Node that is not Stale. This is judged continuously: the Hub is live from the first such reading and stops being live once the last such Node goes Stale.

While a Hub is live:

- **It offers no Replay.** The Hub Panel hides the Event picker and the Replay controls and shows one line instead: "Live Sensors are reporting, so no Replay can play." The Replay routes refuse to start, resume, reset or jump.
- **It stops a Replay that is playing or paused.** The moment the Hub becomes live it announces a stopped Event clock, so every Node stops following the Replay. The Replay's Official Alerts disappear and its Community Warnings stop being filtered by the Event clock, as they do after any stop today.
- **It shows and counts only real Nodes.** The map, the Readings Panel and the status strip leave out every Node whose latest reading is simulated, and Flood Risk and the Hazard trigger read only real readings. A Sensor without hardware, which still sends Simulated Readings from its Replay surface, simply vanishes from a Live Hub's map.

This answers the open question in #89: **a Live Hub hides the Event picker entirely.** It does not offer a "drill" that pauses live readings on screen. A drill would have to hide real water from the people the map serves, for as long as someone forgot to end it. Checking the system and running demos happens on a Hub with no live Sensors: the Sandbox, or a Hub whose Sensors are all simulated.

Separately, **a Region plays only its own Events.** A Hub never takes its Event clock from the Mesh, because it is the only source of the clock. Every other Node ignores an Event clock that names an Event it does not hold, so another Region's Replay never reaches its readings or its map.

When the last real Sensor goes Stale, the Hub stops being live, and the picker comes back. Simulated Nodes reappear only once someone starts a Replay; until then they send the first moment of the first Event, as today.

## User Stories

### Resident (Viewer)

1. As a resident, I want my map to show only real Sensors when real Sensors are reporting, so that I never mistake a Replay's water for the water outside my door.
2. As a resident, I want the Flood Risk to come only from real readings when real readings exist, so that a demo cannot raise or lower the risk I'm shown.
3. As a resident, I want no Community Warning raised by a Simulated Reading while real Sensors report, so that I'm never warned about a flood that is a recording.
4. As a resident, I want no replayed Official Alerts on a live map, so that an old National Weather Service warning is never shown as if it were today's.
5. As a resident using a Sensor's dashboard, I want it to agree with the Hub's about which Nodes show, so that my neighbour's phone and mine tell the same story.
6. As a resident, I want the status strip to count only the real Nodes when the Hub is live, so that "4 real" means four real Sensors.

### Hub operator

7. As the Hub operator, I want the Event picker and Replay controls gone while real Sensors report, so that I can't start a Replay over a live network by mistake.
8. As the Hub operator, I want one line in the Hub Panel saying why the Replay is unavailable, so that I'm not left looking for a missing button.
9. As the Hub operator, I want a Replay that is playing or paused to stop the moment a real Sensor reports, so that a demo left running never overlaps a live reading.
10. As the Hub operator, I want the picker back once the last real Sensor goes Stale, so that a Hub whose hardware is switched off can be used for a demo again without a restart.
11. As the Hub operator, I want the Hub to judge "live" from Registered Nodes only, so that an Unverified Node sending a non-simulated reading can't lock me out of the Replay.
12. As the Hub operator, I want a Stale real Sensor not to keep the Hub live, so that one dead Pi doesn't block demos forever.
13. As the Hub operator, I want the team flood email never sent as a rehearsal while the Hub is live, so that the inbox only gets real warnings from a live network.
14. As the Hub operator, I want my Hub to ignore Event clocks from the Mesh, so that another Region's Hub in radio range can't drive my Replay.
15. As the Hub operator, I want the Event picker to list only my Region's Events, so that I can't play Hurricane Ian on the Bhote Koshi.

### Sensor Node operator

16. As a Sensor Node operator, I want my Node to ignore an Event clock naming an Event it doesn't hold, so that a neighbouring network's Replay never changes what my Node reads.
17. As an operator of a Sensor with no hardware, I want it to keep working in the Sandbox and on a Hub with no live Sensors, so that I can still rehearse with it.

### Team member trying the app

18. As a team member, I want the Sandbox to behave exactly as it does today, so that trying the app is unchanged (every Sandbox Sensor is simulated, so the Sandbox Hub is never live).
19. As a team member, I want a refused Replay control to answer with a clear reason, so that a script or test hitting the API sees why it was refused rather than a bare error.

### Maintainer

20. As a maintainer, I want "live" decided in one place on the Node and handed to the dashboard as a fact, so that the dashboard never re-derives it from the Node list and drifts.
21. As a maintainer, I want the rule tested through the Node API with hand-fed readings, so that it's proven without Pis or sensors.

## Implementation Decisions

- **One rule, judged on every Node.** "Live" is worked out from the Node's own Reading Store snapshot and the Node Registry it has heard: true when any Node in the snapshot is registered, not Stale, and its latest reading is not simulated. It uses the existing Stale window (the one `timing` keeps beside the Flood Risk rule), so a real Sensor stops making the Hub live at the moment it is marked Stale. Every Node judges it the same way from what it hears, so a Sensor's dashboard filters the same Nodes as the Hub's. Only the Hub acts on it (refusing and stopping Replays). The glossary term stays **Live Hub**, because it is the Hub's choice that matters.
- **Registered only.** An Unverified Node's non-simulated reading does not make a Hub live, matching the rule that only Registered Nodes drive community decisions. It is still shown as it is today when the Hub is not live.
- **`/api/state` gains `live: bool`.** It is the dashboard's only signal. While `live` is true, `nodes` holds only the Nodes whose latest reading is not simulated, and `flood_risk` is computed from their readings alone. Nothing else in the state changes shape.
- **The Hazard trigger reads only real readings while live.** The Hub's warning check passes only non-simulated Nodes' readings to the trigger while it is live. A Community Warning already issued during the Replay stays in the Hub's log. No flood email goes out from a Simulated Reading while live, so the rehearsal flag on the email is never set by a Live Hub.
- **Becoming live stops the Replay.** The Hub checks after every reading it keeps. If it is now live and its Event clock is not stopped, it announces a stopped clock (the same `ReplayClockMessage` with `state: "stopped"`). Paused counts as running, because Sensors keep reading the surface at a paused clock's time. The clock's normal repeat carries the stop to Nodes that missed it.
- **The Replay routes refuse on a Live Hub.** Start, resume, reset and jump answer 409 with the detail "live Sensors are reporting, so no Replay can play". Pause has nothing to act on once the Replay has stopped and keeps its existing 409. Rate change is harmless and stays allowed. `/api/replay/events` still lists the Region's Events, so the list is unchanged when the Hub stops being live.
- **The Hub Panel reads `live`.** While it is true, the Replay section shows the one line and no picker, controls or REPLAY label. The Sandbox Panel shares the Replay controls and is never live in practice. It needs no special case.
- **A Hub never takes its Event clock from the Mesh.** Only a Sensor subscribes to Event clocks heard on the Mesh. The Hub's clock moves only through its own routes and its own stop.
- **A Node ignores a clock for an Event it does not hold.** An Event clock naming an Event outside the Node's Region's Events is dropped when heard, not stored. The comment on the clock message already says this; the code is made to match. A Sensor whose Hub plays an Event the Sensor does not hold keeps its previous clock.
- **Own Region only is otherwise already true.** Events are loaded from the Region's own folder and checked against its Hazard and alert sources. Unknown Event ids are refused by the picker routes. This spec pins that with a test rather than changing it.
- **No new wire format.** The `sim` flag on a Community Reading and the stopped Event clock already exist. Wire version stays 2.

## Testing Decisions

- **Good tests here drive Nodes through their HTTP API on the in-memory Mesh and assert what a dashboard would see:** the state, the Replay clock and route answers. They don't reach into the Reading Store or the Event clock object.
- **Node seam (pytest): the existing `MeshedNodes` harness.** Its `hear_from` hand-feeds a reading from a Node that runs no app. It gains a way to send that reading as not simulated, which is the stand-in for a Sensor with real hardware, since no Sensor produces one yet. `register` makes that Node a Registered Node, `advance` moves the clocks past the Stale window, and `announce_replay` sends an Event clock from any sender. One new test module covers:
  - a registered real reading makes the Hub live, and `/api/state` reports `live` and lists only real Nodes;
  - Start, resume, reset and jump answer 409 while live, and a playing or paused Replay is stopped on every Node when the first real reading arrives;
  - Flood Risk and the Hazard trigger ignore a surging simulated Node while live, and no Community Warning or flood email follows;
  - an Unverified Node's real reading does not make the Hub live;
  - the Hub stops being live once the real Node goes Stale, and Start works again;
  - a Hub ignores an Event clock heard on the Mesh, and a Sensor ignores one naming an Event it does not hold;
  - the picker refuses another Region's Event id (prior art: `test_pick_an_event.py`, which already builds a two-Event Region in a temporary folder).
- **Dashboard seam (Vitest): the existing flow tests** that render the app against a mocked `/api/state`. Prior art: `hubPanelFlow.test.tsx` and `replayControlsFlow.test.tsx`. One flow shows that with `live: true` the Hub Panel shows the explanation line and no Event picker, Start button or REPLAY label, and that the picker returns when `live` turns false. The Node list filtering is the Node's job, so the dashboard test does not re-check it.
- **No mesh_integration test.** The rule sits above the Mesh, and the Reticulum path carries the same messages it already carries.
- **Rehearsal:** the real-hardware case is rehearsed with loopback Nodes and a hand-fed non-simulated reading only. No Pi or sensor check is claimed.

## Out of Scope

- **A drill mode** that plays a Replay on a Live Hub while pausing or hiding live readings. Rejected; see Solution.
- **Producing real readings.** Reading a real water-level, rain or soil sensor on a Pi is hardware work (`area: hardware`). This spec only decides what a Hub does once such readings exist.
- **Sensors that stop sending Simulated Readings when no Replay runs.** A hardware-less Sensor still sends the first moment of its first Event. A Live Hub hides it, and a non-live Hub shows it as today.
- **Mixed readings.** A Community Reading is marked simulated only when every Measurement in it is, so a Node mixing one real sensor with simulated ones counts as real and would make a Hub live while carrying simulated values. No Node mixes them today; marking or splitting such readings is left to the issue that first builds a real sensor.
- **Switching Region on a running Hub** (#47 covers the Sandbox's Region picker).
- **Trust between Hubs.** Which Hub a Sensor follows is decided by the existing Hub identity a Sensor is configured with. This spec only stops a Node acting on Events it does not hold.

## Further Notes

- The "never both on one map" acceptance in #89 is met by the filter: a Live Hub's state carries no simulated Node. A Hub that is not live may show simulated Nodes and has no real ones counting toward its live flag. Real Unverified Nodes or Stale real Nodes may still be listed, as they are today.
- `scripts/check.sh` must pass, per the issue.
- The Sandbox never becomes live, since every Sensor it runs is simulated, so the team's main way of trying the app is untouched.
