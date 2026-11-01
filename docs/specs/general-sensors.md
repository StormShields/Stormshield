# General sensors

**Status:** ready-for-agent

From issue #27, the M6 milestone. Words follow `CONTEXT.md`, which this spec adds **Camera** to. The direction is ADR 0006; this picks up decision 9 and the M6 lines of Out of Scope in `docs/specs/regions-events-and-sandbox.md`.

## Problem Statement

ADR 0006 says Storm Shield is a sensor network people run themselves, with flood warning as its first use. The wire format is ready for that: a Community Reading is a list of Measurements, and any kind travels, is stored and is shown. But nobody can see it yet.

- **Only the flood four have a source.** A Sensor's values come from an Event's water surface and weather, which hold rain, soil moisture and pressure and nothing else. A Node set to `NODE_MEASURES=wind_speed` sends nothing. Other kinds have only ever reached the dashboard through hand-fed test readings.
- **A Sandbox Sensor can't be told what it measures.** Everyone who tries the app sees Sensors that all measure the same things, so a farm's weather mast or a Sensor without a rain gauge can't be tried.
- **The dashboard isn't ready for other kinds.** It has labels and Region units for the flood four only. It converts `water_level`, `rain_rate` and `air_pressure` without checking the unit they came in, so a wrong unit shows a wrong number. A kind named `constructor` gets a JavaScript function as its label.
- **Cameras are gone.** M3 deleted the Cameras Panel and its clips, with the promise that cameras would return as sensors.
- **Trying the app still needs a terminal.** The Sandbox takes one command, but that command needs a checkout, `bash`, `uv` and `pnpm`. The project's own brief says trying the app must not need a terminal.

## Solution

**Three new kinds, and any other still works.** `air_temperature`, `humidity` and `wind_speed` join the flood four as kinds the dashboard knows, with labels and Region units. A kind the dashboard doesn't know is still shown under its own name, with its own unit.

**Events can carry any kind.** An Event file can hold extra measurement tracks. The made-up Events gain the three new kinds. Real Events stay as they are, because their tracks are rebuilt from records and nobody has researched these kinds for them.

**A Sandbox Sensor measures what you tick.** Each Sensor in the Sandbox Panel has a list of the kinds on offer. Unticking rain makes it a Sensor with no rain gauge: it sends no rain, and its reading is smaller.

**No second Rule set.** No real use needs one today: nobody has asked for a warning on anything but water, and the Sandbox's new kinds are there to be seen, not to warn. Flood warning stays the only Rule set, it keeps ignoring kinds it doesn't know, and no rule engine or plugin point is built. The first real request for a non-flood warning is what opens that work.

**A Camera is a Sensor Node that declares the `camera` kind.** It registers, sits on the map and signs its readings like any other Sensor. Its reading says only that a new picture exists. The picture itself stays on the Node and never crosses the Mesh. This milestone's pictures are drawn, not photographed: the Node draws a small labelled scene from the water level at its own spot, so there's no footage to pass off as real and nothing private to leak.

**A double-click starts the Sandbox.** A Windows and a macOS download, published on a GitHub Release, each hold the whole Sandbox: Python, the built dashboard, the Regions and their Cache Packs. Opening it starts the Sandbox on this machine only and opens the browser. Nothing else needs installing, and the download works with no internet after that. A Stop button in the Sandbox Panel ends it, and it also ends itself once no dashboard has asked for anything for a while.

## User Stories

### Someone trying the app

1. As someone trying the app, I want to download one file and double-click it, so that I can try Storm Shield without a terminal, a checkout or any developer tools.
2. As someone trying the app, I want the dashboard to open in my browser by itself, so that I don't need to know a port or an address.
3. As someone trying the app, I want it to work with no internet after the download, so that the offline story is true on my own machine.
4. As someone trying the app, I want the download page to tell me how to get past my computer's warning about an unsigned app, so that I don't think the download is broken.
5. As someone trying the app, I want a Stop button, so that I can end it without hunting for a process.
6. As someone trying the app, I want it to end by itself after I've closed the tab, so that it doesn't stay running for days.
7. As someone trying the app, I want opening it a second time to bring me to the one already running, so that I don't end up with two.
8. As someone trying the app, I want it to find another port when something else already holds its usual one, so that it starts anyway.
9. As someone trying the app, I want a failed start to show me what went wrong in my browser, so that it isn't an app that silently does nothing.
10. As someone trying the app, I want it reachable only from my own machine, so that trying it doesn't open anything to my network.

### Sandbox Sensors

11. As someone trying the app, I want each simulated Sensor to list the kinds it can measure, so that I can see what a different Sensor would be like.
12. As someone trying the app, I want to untick a kind on one Sensor and see it disappear from that Sensor's readings, so that a Sensor without a rain gauge is something I can try.
13. As someone trying the app, I want a new Sensor to start with every kind the Event offers, so that I see the most with the least clicking.
14. As someone trying the app, I want only the kinds the playing Event supplies on offer, so that I'm not offered a kind that would never send anything.
15. As someone trying the app, I want one Sensor to be a Camera from the start, so that I find Cameras without looking for them.

### Reading the new kinds

16. As a Viewer, I want air temperature, humidity and wind speed in the Readings Panel and on the map with proper names, so that I can read them at a glance.
17. As a Viewer in Fort Myers, I want °F and mph, so that the numbers mean something to me.
18. As a Viewer in Nepal, I want °C and km/h, so that the numbers mean something to me.
19. As a Viewer, I want a kind the dashboard has never heard of still shown with its own name and unit, so that a new sensor is useful before anyone changes the dashboard.
20. As a Viewer, I want a known kind sent in an unexpected unit shown as it was sent, so that I'm never shown a wrongly converted number.
21. As a resident, I want the new kinds to change nothing about Flood Risk or Community Warnings, so that a hot, windy day can't raise a flood warning.

### Cameras

22. As someone trying the app, I want to open a Camera from its Sensor's row and see its newest picture, so that I know what a Camera adds.
23. As a Viewer, I want a Camera's picture marked SIMULATED, in the picture itself and beside it, so that a drawing is never taken for a photograph.
24. As a Viewer, I want the picture to change as the water rises at that Camera's spot, so that it says something about the Event.
25. As a Viewer, I want a Camera's row to say only that it has a picture, with no rising or falling arrow, so that a picture counter doesn't look like a measurement going up.
26. As someone whose position is fuzzed, I want pictures to stay on the Camera's own Node, so that a picture can't undo the fuzzing by showing the Mesh where I am.

### Region and Event authors

27. As an Event author, I want to add a track of any kind and unit to an Event file, so that a new kind needs no code change.
28. As an Event author, I want a bad track (a flood kind repeated, times out of order, a non-finite value) to fail when the Event is loaded, with a message naming it, so that I find out at once.
29. As a Region author, I want no new required lines in my Region file, so that existing Regions and published Cache Packs stay valid.

### Maintainers

30. As a maintainer, I want a reading too big for one packet to fail the same way in the Sandbox as on real Reticulum, so that the Sandbox can't hide it.
31. As a maintainer, I want every download built by CI from a clean checkout, so that nothing from anyone's laptop, `.env` above all, can end up in it.
32. As a maintainer, I want CI to start each built download and check its Hub answers, so that a broken download never gets published.
33. As a maintainer, I want `scripts/sandbox.sh` to keep working as it does now, so that nobody working from a checkout loses anything.

## Implementation Decisions

### 1. The kinds

| Kind | Wire unit | Label | Shown as (Region's `distance` is km) | Shown as (Region's `distance` is mi) |
|---|---|---|---|---|
| `air_temperature` | °C | Air temperature | °C | °F |
| `humidity` | % | Humidity | % | % |
| `wind_speed` | m/s | Wind speed | km/h | mph |
| `camera` | pic | Camera | "Picture 57" | "Picture 57" |

- **Why these:** they are what a farm, remote land or a coast would measure first, and they have an honest unit everywhere. Soil temperature, wind direction, leaf wetness and the like work as unknown kinds without any change. Add one to this table when someone needs it to read better.
- **`humidity`, not `relative_humidity`:** with the long name, a reading holding all eight kinds measures 358 bytes, over the 350-byte budget. With `humidity` and `pic` it's about 345. This budget is why the names are short.
- **Region units follow the Region's `distance`.** The dashboard's speed formatting already does this. `display_units` doesn't change, so no Region file, Cache Pack or checked-in fixture needs rebuilding.
- **No wire format change.** Reading version stays 2, because `m` already carries any kind. Registration stays as it is: the Hub learns a Node's kinds by seeing them in its readings. "Declares" keeps meaning the Node's own configuration (`NODE_MEASURES`), which stays at the flood four by default for a Node outside the Sandbox.

### 2. Event tracks

- An Event file gains an optional list of measurement tracks. Each has a kind, a unit, a number of decimals and a series of time and value pairs. A track is one value for the whole Region at a given time, on straight lines between points, as the weather is.
- Loading refuses a track that repeats a flood kind or another track's kind, has times out of order, or holds a non-finite value. The error names the Event and the track.
- `camera` is refused as a track too, since the Node makes that one itself (decision 4).
- The made-up Events of both Regions gain `air_temperature`, `humidity` and `wind_speed` tracks that fit their story. Their numbers are made up, as everything in those files is. Real Events (Ian, Bhote Koshi) get no tracks.
- A Node sends a track only when its `NODE_MEASURES` names it, the same filter the flood four already pass through. Flood kinds keep their present source.

### 3. Sandbox Sensors declare their kinds

- A Sensor's declared kinds can change while it runs, so they are asked for at each share, the way position already is.
- The Sandbox's Node list gains, for each Sensor, what it declares, and overall, what the current Event offers (its flood kinds, its tracks, and `camera`).
- Adding or editing a Sensor through the Sandbox API takes an optional list of kinds. A kind not on offer is refused with a sentence saying so.
- A new Sensor declares everything on offer except `camera`. The Sandbox's first Sensor also declares `camera`.
- The Sandbox Panel shows each Sensor's kinds as a list of tick boxes in its row. Follow `design-rules`, and keep the row usable at phone width.
- A Sensor remembers the kinds someone unticked and declares everything else on offer, so switching Event just applies the new offer. Switching Region starts new Sensors, as it does today, with nothing unticked.

### 4. Cameras

- **Glossary:** a **Camera** is a Sensor Node that declares the `camera` kind. Its readings say a new picture exists. The picture stays on the Node.
- **The Measurement:** `["camera", <picture number>, "pic"]`. The number goes up by one per picture and starts at 1 on the Node's start. Rules ignore it as they ignore any unknown kind.
- **The picture:** one small SVG, the newest only, held in memory. The Node draws it at each share from the water level at its own spot and the Event time: a water line against a depth staff, or dry ground when the spot is dry. "SIMULATED" is part of the drawing. It holds no coordinates, Node id, or real place name. It's sent as `image/svg+xml` and shown through an `<img>`, so a script inside it can't run.
- **Routes:** a Node declaring `camera` answers one read-only route with its newest picture and 404s otherwise. The Sandbox's Hub passes on its Sensors' pictures through one Sandbox-only route, because the Hub is the only dashboard the Sandbox serves. The picture passes through in-process, regardless of radio range, and the panel says "Stays on this Camera; it does not cross the Mesh".
- **Dashboard:** a Sensor's row reads "Camera: Picture 57" with no trend arrow. In the Sandbox, tapping that row's line opens the picture, and it refreshes when the number changes. There's no Cameras Panel. Outside the Sandbox a Viewer sees the picture only for the Node they're connected to.
- **Live Hub:** a Camera's readings are Simulated Readings, so a Live Hub hides them as it hides any others. Nothing else changes.
- **Why the picture stays on the Node:** single signed packets carry 400 bytes of JSON at most, so a picture would mean new Mesh transport. More importantly, a picture can show where someone is, and the Mesh carries only a Fuzzed Position to protect that. Who may see a real camera's picture, and whether pictures may leave their Node, is a privacy decision for the project's owner, to be asked when real cameras are built (see Out of Scope).

### 5. The dashboard and unknown kinds

- Label lookups and conversions treat a kind as data: only a label or unit defined for that kind counts, so `constructor` or `__proto__` reads as its own name.
- A known kind converts only when it arrives in its wire unit. Otherwise it's shown as sent. This covers the flood kinds too, closing the conversion gap described above.
- The trend arrow skips `camera`. All other kinds keep it.
- The Readings Panel row wraps when a Sensor sends all eight kinds, and stays readable at phone width.

### 6. Readings too big to send

- The in-memory Mesh refuses a message over the packet limit, using the same limit and the same error as real Reticulum, so the Sandbox can't hide it. Today it has no check.
- A Node whose reading won't fit logs an error once per cause and shares nothing for that tick, rather than crashing its publishing loop or trimming the reading. The other Nodes carry on.
- A test holds a reading with all eight kinds, at realistic values, under the 350-byte budget of the wire format.

### 7. The Sandbox app

- **Packaging:** PyInstaller, one folder per platform, zipped: a `.app` for macOS on Apple Silicon and a windowed `.exe` for Windows x64. Each is built on that platform's GitHub Actions runner, since PyInstaller can't cross-build. It holds its own Python, the Node package, the built dashboard, `regions/`, and the current Cache Pack of each built-in Region (4 MB and 6 MB today), so there's no first-run download.
- **Finding its files:** the Sandbox currently finds the dashboard, Regions and packs relative to the repo checkout. That becomes one module that answers "where do the app's files live" for both a checkout and a bundle. `scripts/sandbox.sh` keeps today's behaviour.
- **App start:** a new entry point for the bundle wraps the existing Sandbox start, with no arguments:
  - It picks port 8000, or a free one if something else holds it. If a Sandbox already answers on 8000, it opens the browser there and exits.
  - On any start failure it writes a small page holding the error and the log's path to a temp folder, and opens that in the browser. There's no native dialog code.
  - It logs to a file in the user's temp folder, since there's no terminal to read.
- **Network:** the Sandbox stays bound to loopback, as it is today. A test holds it there. The app offers no way to widen it.
- **Stopping:**
  - A Stop button in the Sandbox Panel, shown only when running as the app, posts to a Sandbox-only route that ends the process. The route refuses a request that isn't from loopback or whose `Origin` isn't its own, so another website the browser has open can't stop it. After Stop, the page says it's safe to close.
  - The app ends itself after 10 minutes with no `/api/state` request. Browsers still poll in a background tab, at a reduced rate, so this doesn't fire while a tab is open. A laptop waking from sleep may find it gone; the dashboard's existing "can't reach" state covers that, and opening the app again starts over.
  - Its temp folder is removed on both paths, as it is today.
- **Unsigned on purpose:** signing and notarising need paid accounts, so neither is done. The download page gives the steps past Windows SmartScreen and macOS Gatekeeper (System Settings → Privacy & Security → Open Anyway). Those steps use no terminal.
- **Publishing:** a workflow builds both platforms from a clean checkout, runs the smoke check below, and publishes a Release tagged `sandbox-app-v<N>`, marked not latest so it doesn't take that mark from anything else. It runs by manual dispatch with the version number, and as a build and smoke check with no publishing on any pull request touching the packaging. The first Release is dispatched right after the slice merges, and that slice isn't finished until it exists.
- **Smoke check in CI:** start the built app on each runner with `BROWSER` or its platform equivalent stubbed. Check the Hub's `/api/state` reports a `sandbox` with Sensors on it, check a switch to the other Region succeeds using the bundled pack, check Stop ends the process, and check the temp folder is gone. Fail the workflow on any of these.
- **README:** a "Try it" section at the top links the Release, with the warning steps. `AGENTS.md` keeps the commands for people with a checkout.

### 8. Glossary and docs

The spec's PR adds **Camera** to `CONTEXT.md`. The slices update the **Sandbox** entry ("one command" gains the app), the **Measurement** examples and `docs/specs/wire-formats.md` (the known kinds and the `camera` Measurement) in the PR that makes each one true. No ADR is needed: ADR 0006 already holds the direction, and this adds no alternative to it.

## Acceptance Criteria

Kinds and Events:

- [ ] A made-up Event plays and a Sandbox Sensor sends `air_temperature`, `humidity` and `wind_speed` in their wire units; `/api/state` holds them under that Node.
- [ ] The Ian and Bhote Koshi Events load unchanged and their Sensors send no new kinds.
- [ ] A Node with `NODE_MEASURES` naming a track sends it, and one not naming it doesn't.
- [ ] An Event file with a bad track (flood kind or `camera` repeated, times out of order, a non-finite value) fails to load with a message naming the Event and track.
- [ ] Flood Risk and Community Warnings come out identical with and without the new kinds on the same Event.
- [ ] A reading with all eight kinds at realistic values is under 350 bytes.
- [ ] An oversized reading is refused by the in-memory Mesh with the same error as real Reticulum; the Node logs it, shares nothing that tick and keeps running.
- [ ] No Region file, Cache Pack or checked-in fixture changes.

Dashboard:

- [ ] The new kinds show with their labels: °C and km/h on Nepal, °F and mph on Fort Myers.
- [ ] A kind the dashboard doesn't know shows as its own name and unit, including kinds named `constructor` and `__proto__`.
- [ ] `water_level`, `rain_rate`, `air_pressure`, `air_temperature` or `wind_speed` sent in a unit other than its wire unit is shown as sent, not converted.
- [ ] `camera` has no trend arrow. Every other kind keeps its arrow.
- [ ] A Sensor row with all eight kinds is readable at phone width.

Sandbox Sensors:

- [ ] The Sandbox Panel lists each Sensor's kinds; unticking one stops that kind in its next reading, and `/api/state` stops listing it.
- [ ] A kind not on offer is refused by the API with a readable sentence.
- [ ] A new Sensor declares everything on offer except `camera`, and the first Sensor also declares `camera`.
- [ ] A Region or Event switch leaves every Sensor's kinds within the new offer.

Cameras:

- [ ] A Node declaring `camera` sends `["camera", n, "pic"]` with `n` going up per share, and its picture route returns an SVG. A Node not declaring it returns 404 and sends no such Measurement.
- [ ] The SVG holds "SIMULATED", differs between a wet and a dry spot, and holds no coordinates or Node id.
- [ ] No picture bytes pass through the Mesh: the only `camera` data on the Mesh is the Measurement.
- [ ] In the Sandbox, the row's Camera line opens the picture marked SIMULATED, with the "Stays on this Camera" line, and it changes when the number changes.
- [ ] A Live Hub shows no Camera rows from simulated Nodes.
- [ ] The Rule set never reads `camera`.

The app:

- [ ] CI builds the Windows and macOS downloads from a clean checkout, and the smoke check passes on both.
- [ ] Each download holds both Regions' Cache Packs and no `.env`, and CI checks it.
- [ ] The Sandbox binds loopback only, and a test holds this.
- [ ] A second start with a Sandbox on 8000 opens that one and exits; a start with something else on 8000 serves on a free port.
- [ ] A start failure opens a page in the browser holding the error and the log's path.
- [ ] Stop ends the process and removes its temp folder. The route refuses a foreign `Origin` and a non-loopback client. Outside the app the Stop button isn't shown and the route isn't there.
- [ ] With no `/api/state` request for 10 minutes, the app ends itself and removes its temp folder (test with a short interval or a fake clock).
- [ ] `scripts/sandbox.sh` still works from a checkout, unchanged.
- [ ] A `sandbox-app-v1` Release exists, not marked latest, and the README's "Try it" section links it with the warning steps.
- [ ] A person double-clicks each download on a real Windows and macOS machine and reports it in the PR. Until then, the PR says this is unproven.

## Testing Decisions

- **A good test here starts a Node and looks at what it says,** through the API and the Mesh, not at private functions.
- **Node seam (pytest), the main one:** `MeshedNodes` and `/api/state`. Prior art: `test_community_reading`, `test_state_snapshot`, and the `hear_from(..., also=[...])` hand-fed readings. Event track validation uses the same tests as the current Event loading.
- **Sandbox seam (pytest):** the Sandbox's HTTP API, as its tests already do, for kinds, pictures, Stop and the idle end. The idle end uses the `clock` the Node already takes, so no test waits 10 minutes.
- **Dashboard seam (Vitest):** `nodesOnMap`, `kindLabel` and `displayUnits` as pure functions for conversions and odd kind names; the existing Sandbox Panel and Readings Panel flow tests for tick boxes and the Camera line.
- **App seam (CI):** the smoke check in decision 7 is the only test of the bundle. It runs in its own workflow, because `scripts/check.sh` stays quick and platform-free.
- **Not provable by agents:** double-clicking past SmartScreen and Gatekeeper needs a person on the machine. Say so in the PR and never report it as passed. Nothing in this milestone needs a Pi or a sensor.
- **`mesh_integration`:** rerun it for the slice that changes reading publishing or the packet limit, since CI doesn't.

## Out of Scope

- **A second Rule set, a rule engine, or plugin points.** See Solution.
- **Real sensors and real cameras.** Reading real hardware is `area: hardware` work and stays out, as it is in the regions spec. That includes capturing real pictures.
- **Moving pictures anywhere off their Node:** no Mesh transfer, no Hub copy, no history. Before anyone builds that or real capture, the project's owner decides who may see a real camera's picture, because it's a privacy question.
- **Research for the new kinds on real Events.** Ian and Bhote Koshi stay as they are.
- **Signing and notarising the downloads.** Those need paid accounts.
- **Linux and Intel Mac downloads, auto-update, installers.** Linux keeps `scripts/sandbox.sh`. Add a platform when someone needs one.
- **A Region or port chooser in the app.** The Sandbox Panel already switches Region.
- **Exposing the Sandbox to the local network from the app.**
- **A hosted service of any kind.**

## Further Notes

- **Suggested order for splitting:** Event tracks and the packet limit first, since everything else needs values to show. Then dashboard kinds and units, Sandbox tick boxes, and Cameras. The app work stands alone: file locations and app start first, then Stop and the idle end, then the workflow and Release. Add the README section last, since it needs the Release.
- **Who it's for:** Sandbox app work is `area: workflow`, Event tracks and the Node's Camera are `area: node`, and dashboard work is `area: dashboard`.
- **Security review:** the app slices add a route that ends the process and a public binary download, so they ask for one under the company's rule.
