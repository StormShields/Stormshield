# Regions, Events and the Sandbox

**Status:** ready-for-agent

From issue #21 (grilling done 20 Oct 2026). Words follow `CONTEXT.md`; the direction is ADR 0006 (a general sensor network, flood warning first). It replaces the hard-wired Nepal valley of `docs/specs/flash-flood-replay.md` with Regions and Events. That spec, and ADR 0004, now describe the Nepal Region only. The Mesh, the Hub, Registered and Unverified Nodes, signatures, the Household Profile staying on the device, and "only official sources order evacuation" all still hold.

## Problem Statement

Storm Shield is a working demo of one place and one day: the Bhote Koshi valley on 26 August 2026. Everything about that place is written into the code: the valley's bounds, the river line and River km, Nepal time, metric units, the DHM and NDRRMA alert sources, the flash-flood thresholds (300 cm in 60 s) and four Replay tracks pinned to four Nodes.

That causes three problems for the team.

- **Nobody can try the app without a terminal session of their own.** A hand check means stopping stray Nodes, serving a Cache Pack, starting a Hub, starting each Sensor with its own port, loopback slot and data dir, and copying `HUB_IDENTITY` into each of them. Most of the team doesn't, so the dashboard gets checked by the one person who can.
- **The app can't be pointed at a new place.** Someone with a farm, a creek or a stretch of coast would have to edit Python, TypeScript and build scripts, and the flood rules would still assume a Himalayan river.
- **The readings are flood-shaped.** A Community Reading has exactly four fields (water level, rain, soil moisture, pressure). A Sensor Node that measures anything else has nowhere to put it, which blocks the general sensor network ADR 0006 commits to.

The demo also carries parts that only made sense on stage: a Simulated Fleet of 40 display-only Nodes, illustrative camera clips, and a breadboard that steps a scripted Scenario.

## Solution

A **Region** is one small hand-written file, `regions/<name>/region.json`. It gives the place's area, time zone, display units, official alert source, the water it watches (a river or a coast), the thresholds its Rule set uses, its Shelters, its suggested sensor sites, where its Hub runs and its data sources. One build command turns it into the Region's Cache Pack. Packs for the built-in Regions are published as GitHub Releases. Adding a place means writing that file, not code.

The first new Region is **Fort Myers**: Fort Myers Beach and Estero Bay, from downtown Fort Myers to Bonita Springs. Its first Event is **Hurricane Ian's storm surge on 28 September 2022**. Fort Myers is the default Region and the one the tests use. Nepal stays as a second Region only as far as moving it is mechanical.

An **Event** is one happening at a Region, of one **Hazard** (a flash flood or a storm surge). It is played as a **Replay**: a water surface plus weather over time, played on the Event clock. Each Sensor Node reads its Simulated Readings from that surface at its own position, so a Sensor on high ground stays dry and one at the bay shore floods first. The Hazard names the Community Warning and picks what triggers it:

- a **flash flood** is triggered by a Surge;
- a **storm surge** is triggered by the water level passing a set height while rising.

On a coast, each resident's **Water ETA** compares the rising water level with the ground height at their home: "Water reaches your ground in about 2 h 10 min".

A **Community Reading** becomes a timestamped list of **Measurements**, each with a kind and a unit. Flood warning (Flood Risk, Surges, Community Warnings) is the first Rule set. It reads the kinds it knows, ignores the rest, and takes its thresholds from the Region's file.

The **Sandbox** lets anyone try all of this with one command, and without knowing the Mesh's plumbing. It starts a Hub and simulated Sensors in one process on a shared in-memory Mesh and opens the dashboard. From there the user can:

- pick a Region;
- place and drag Sensors on the map;
- set the radio range (about 1 km by default), with messages hopping from Node to Node and range circles and links drawn on the map;
- pick an Event and play it on the Event clock.

The Simulated Fleet, the camera clips and Cameras Panel, and the breadboard and Scenario are deleted, each together with its tests.

## User Stories

### Team member trying the app

1. As a team member, I want one command to start a Hub and simulated Sensors, so that I can try the app without juggling ports, loopback slots, data dirs or Hub ids.
2. As a team member, I want the Sandbox to open the dashboard for me, so that I go straight from the command to the map.
3. As a team member, I want the Sandbox to start on the Fort Myers Region by default, so that the first thing I see is the Region the tests use.
4. As a team member, I want the Sandbox to place Sensors at the Region's suggested sensor sites at start, so that an Event can be played at once without setting anything up.
5. As a team member, I want every Sandbox Sensor registered automatically, so that I don't have to accept Sign-ups before readings count.
6. As a team member, I want the Sandbox to use the Region's Cache Pack from disk, or download it from its Release while online, so that I never run a pack server.
7. As a team member, I want a clear message when the Region's pack is neither on disk nor downloadable, telling me the build command, so that I know how to get it.
8. As a team member, I want to add a Sensor by tapping the map, so that I can test a spot the suggested sites don't cover.
9. As a team member, I want to drag a Sensor to a new spot, so that I can see how its readings change between the shore and higher ground.
10. As a team member, I want to remove a Sensor, so that I can see what happens when a part of the Mesh is missing.
11. As a team member, I want to see the suggested sensor sites as faint markers I can turn into Sensors, so that I place Sensors where the Region's author meant them to go.
12. As a team member, I want a radio range slider (about 1 km by default), so that I can see how far apart Sensors can be and still hear each other.
13. As a team member, I want each Node drawn with its range circle, so that I can see at a glance who can hear whom.
14. As a team member, I want a line drawn between every two Nodes in range of each other, so that I can see the paths a message can take.
15. As a team member, I want messages to hop through other Nodes, so that a Sensor out of the Hub's range still gets through when a neighbour relays.
16. As a team member, I want a Sensor with no path to the Hub clearly marked, so that I see why its readings never reach the Hub.
17. As a team member, I want the Sandbox's Node list to show, for each Node, whether it has heard the latest Community Warning, so that I can check the warning reached everyone in range.
18. As a team member, I want to pick an Event from the Region's list and play it from the dashboard, so that I can rehearse it without editing files.
19. As a team member, I want to play, pause, reset, change the speed and jump to a named phase of the Event, so that I can go straight to the moment I'm testing.
20. As a team member, I want to switch Region from the dashboard, so that I can try Nepal and Fort Myers in one sitting.
21. As a team member, I want everything in the Sandbox labelled SIMULATED and every Event labelled REPLAY, so that no screenshot passes for a live flood.

### Region author

22. As a Region author, I want to describe a new place in one hand-written file, so that adding a Region needs no code.
23. As a Region author, I want to set the Region's area as a bounding box, so that the map, the pack and the weather all cover the same land.
24. As a Region author, I want to set the Region's time zone, so that the Event clock and alert times read in local time ("28 Sep 2022 · 14:06 EDT").
25. As a Region author, I want to set the Region's display units (feet and miles for Florida, metres and kilometres for Nepal), so that residents read numbers they understand.
26. As a Region author, I want to name the official alert source (the National Weather Service in Florida, DHM in Nepal), so that Official Alerts are credited correctly.
27. As a Region author, I want to say whether the Region watches a river or a coast, so that Water ETA and the Flood-Prone Area are worked out the right way.
28. As a Region author, I want to write the Rule set's thresholds in the Region's own units (a storm-surge warning height in feet), so that I don't convert by hand and get it wrong.
29. As a Region author, I want to list the Region's Shelters with their positions and kinds (special-needs, pet-friendly), so that the Evacuation Plan can offer them.
30. As a Region author, I want to list suggested sensor sites, so that a new network starts with Sensors where they help most.
31. As a Region author, I want to list the Region's data sources (terrain, roads, weather, gauges, warnings) with their credits, so that the build knows where to fetch from and the app credits them.
32. As a Region author, I want one build command to turn the Region file into its Cache Pack, so that I don't learn the packing scripts.
33. As a Region author, I want the build to say plainly which source failed and why, so that a flaky download isn't mistaken for a broken Region.
34. As a Region author, I want built-in Regions' packs published as Releases, so that nobody else has to run the build.
35. As a Region author, I want to hand-write a made-up Event file for my Region, so that I can test the network on a flood that never happened.
36. As a Region author, I want the build to check my Region and Event files against their schema and name the bad field, so that a typo doesn't surface as a blank map.

### Resident on a coast (Viewer)

37. As a resident of Fort Myers Beach, I want to be told when the water reported over the Mesh is rising towards my ground, so that I can leave before it reaches my door.
38. As a resident, I want my Water ETA in hours and minutes ("Water reaches your ground in about 2 h 10 min"), so that a slow storm surge reads the way it unfolds.
39. As a resident, I want the Water ETA to say what it's based on (the level now, how fast it's rising, my ground height), so that I can check the reasoning.
40. As a resident, I want my ground height looked up on my own phone from the Cache Pack, so that my home location never leaves my device.
41. As a resident, I want "Water is at your ground now" once the level reaches my ground height, so that I never see a negative or frozen number.
42. As a resident, I want no Water ETA while the water isn't rising, so that a high tide that has turned doesn't count down to nothing.
43. As a resident, I want the Flood-Prone Area shown as the land below a set height, marked approximate, so that I can see which streets the water reaches first.
44. As a resident, I want Shelters inside the Flood-Prone Area never offered, so that I'm never sent towards the water.
45. As a resident, I want the Community Warning titled "Storm Surge · Community Warning · not official", so that I know it's a storm surge and that it isn't an evacuation order.
46. As a resident, I want National Weather Service warnings for Lee County shown in their official style with their real times, so that I can compare them with the Community Warning.
47. As a resident, I want NOAA tide gauges shown on the map as Official Gauges, visibly different from Community Readings, so that I can see the official level next to my neighbours'.
48. As a resident, I want Official Gauges never counted toward Flood Risk, so that only Registered Nodes drive community warnings.
49. As a resident, I want water levels in feet and distances in miles, so that I read the numbers I know.

### Resident on a river (Viewer)

50. As a resident on the Bhote Koshi, I want my Water ETA to keep working the way it does today (the Surge's arrival at my home on the river line), so that the river Region loses nothing.
51. As a resident on a river, I want the Community Warning titled "Flash Flood", so that I know what kind of water is coming.

### Sensor Node operator

52. As a Sensor Node operator, I want my Node to declare the kinds it measures, so that a Sensor without a rain gauge simply doesn't send rain.
53. As an operator, I want readings of kinds the Rule set doesn't know shown on the dashboard anyway, so that a new sensor is useful before any rule reads it.
54. As an operator, I want my Node to get its Region from the Hub's Cache Pack, so that I configure the Region once, on the Hub.

### Hub operator

55. As the Hub operator, I want to choose my Region in one setting, so that a real Hub runs the place I live in.
56. As the Hub operator, I want to pick an Event from the Region's list in the Hub Panel and play it, so that the same controls run any Region's Replay.
57. As the Hub operator, I want the Hub to issue one signed Community Warning when the Hazard's trigger fires on a Registered Node, so that no time is lost waiting for a second Node.
58. As the Hub operator, I want the Hub to bring live NOAA tide gauge levels into the Mesh while it's online, so that residents keep the last official level after the internet goes down.
59. As the Hub operator, I want an Event's Official Alerts to appear on the Event clock at their real times, so that the gap between community and official warnings shows.

### Maintainer

60. As a maintainer, I want the tests to start Nodes through the same Sandbox the team uses by hand, so that one harness is kept working, not two.
61. As a maintainer, I want the tests to use the Fort Myers Region, so that the default Region is the one that's always green.
62. As a maintainer, I want the Simulated Fleet, camera clips, Cameras Panel, breadboard and Scenario deleted with their tests, so that no time goes into code the redesign removes.
63. As a maintainer, I want the reading wire format to change once, early, so that every Event file and Sandbox screen is written against the final shape.
64. As a maintainer, I want the original Nepal demo still runnable from the `v0-swamphacks` tag, so that deleting Nepal-only code loses nothing we can't get back.

## Implementation Decisions

### 1. Generic readings: Measurements and the flood-warning Rule set

- **A Community Reading is a timestamped list of Measurements.** Each Measurement is a kind, a value and a unit. The four fixed fields (`water_m`, `rain_mmh`, `soil_pct`, `pressure_hpa`) go.
- **Each kind the Rule set knows has one wire unit:**

  | Kind | Wire unit |
  |---|---|
  | `water_level` | m |
  | `rain_rate` | mm/h |
  | `soil_moisture` | % |
  | `air_pressure` | hPa |

  Region display units convert on screen only. The Rule set ignores a known kind sent in a different unit and logs it once per Node. A kind it doesn't know is carried, stored and shown with its own unit, and never read by a rule.
- **A Sensor Node declares the kinds it measures in its configuration.** In the Sandbox, the default for each simulated Sensor is all four. Nothing in the Mesh assumes a fixed list.
- **The new wire format is version 2.** Measurements are sent as compact `[kind, value, unit]` triples so a full reading stays far under the 464-byte packet cap. Position stays fuzzed. `river_km` stays and is null on a coast Region. Shape:

  ```json
  {"v": 2, "kind": "reading", "node": "a1b2c3d4e5f6", "seq": 812, "t": 1664373960,
   "sim": true, "pos": [26.452, -81.948], "river_km": null,
   "m": [["water_level", 2.41, "m"], ["air_pressure", 968.2, "hPa"], ["rain_rate", 38.0, "mm/h"]]}
  ```

  Version 1 readings are dropped. Every Node is upgraded together, because no fielded Nodes exist.
- **On a coast, `water_level` is the water surface height above the Region's datum.** On a river it stays the stage at the Sensor. A Sensor whose spot is dry sends no `water_level` Measurement (it isn't zero), and the dashboard shows it as dry.
- **`/api/state` keeps `measurements` keyed by kind, but only the kinds a Node sent.** Values are in the wire unit (water level in m, where it was cm before). The `Reading` type and `ReadingKind` move out of the Scenario module into the reading module, since the Scenario is deleted.
- **The two exact-field tests change in the same PR as the wire format.**
  - `test_community_reading` asserts the version 2 field set, the size bound, and that the Measurements come back unchanged.
  - `test_state_snapshot` asserts a Node entry holds exactly the kinds its Sensor declared. The top-level `scenario` and `fleet` keys are gone; `region`, `hazard` and (in the Sandbox only) `sandbox` are added.
- **Flood warning is the one Rule set.** It holds Flood Risk, Surge, Raining, Storm Signal and the Hazard triggers below. Its thresholds stop being module constants and are read from the Region's file at start. No rule engine or plugin point is built: a second Rule set waits for M6.
- **Display text sentences** (Flood Risk reasons, the warning title) take the Hazard and the Region's display units.

### 2. The Region file and its Cache Pack

- **A Region is `regions/<name>/region.json`, hand-written and checked against a schema at build and at Node start.** Raw source files sit beside it in `regions/<name>/sources/`, and hand-written Events in `regions/<name>/events/`. The file carries:
  - `name`, `label` and `bbox` (south, west, north, east).
  - `time_zone` (IANA, e.g. `America/New_York`) and `display_units` (per kind and for distance).
  - `official_alert_source`: its name, short tag and the zones or areas it covers.
  - `water`, either `{ "type": "river", ... }` (river line source, River km origin, corridor) or `{ "type": "coast", "datum": "NAVD88", "flood_prone_below": { "value": 9, "unit": "ft" } }`.
  - `rules.flood_warning`: thresholds per Hazard, each written with its unit. Shape:

    ```json
    "rules": { "flood_warning": {
      "storm_surge": { "warning_height": {"value": 4, "unit": "ft"},
                       "rising":         {"value": 0.5, "unit": "ft"}, "rising_window_s": 900,
                       "elevated_level": {"value": 3, "unit": "ft"},
                       "high_level":     {"value": 6, "unit": "ft"} },
      "rain_elevated": {"value": 0.4, "unit": "in/h"}, "rain_high": {"value": 1, "unit": "in/h"},
      "storm_pressure": {"value": 1000, "unit": "hPa"}, "soil_rising_points": 3 } }
    ```

    A river Region has a `flash_flood` block instead (`surge_rise` 300 cm, `surge_window_s` 60, plus Elevated, High and rising levels). These are today's constants, moved. The Fort Myers numbers above are placeholders for the first ticket to set from the NWS storm-surge categories.
  - `shelters` (id, name, position, kinds). They are hand-picked; a Shelter must lie outside the Flood-Prone Area.
  - `high_ground` (optional) and `sensor_sites` (id, label, position, why).
  - `hub_site`, where the Region's Hub runs, in a sensor site's shape (Dunbar High School for Fort Myers, Betrawati for Nepal). The Sandbox starts its Hub there.
  - `official_gauges` (agency, station id, label, position, datum offset).
  - `sources` (terrain, roads, basemap, weather, gauges, warnings), each with a URL and a credit.
- **The Region's water type picks the live Hazard**: a river means a flash flood, a coast means a storm surge. An Event's Hazard must be one the Region has thresholds for.
- **One build command makes a Region's Cache Pack from its file**, e.g. `build-cache-pack fort-myers`. It replaces today's Nepal-wired `build_cache_pack.py` constants with values read from the Region. The pack holds:
  - the Region file itself, so Sensor Nodes learn the Region from the Hub's pack and are never configured with it;
  - a generic basemap for the bbox (land and water, roads, place labels) from OpenStreetMap;
  - terrain (Terrarium elevation tiles);
  - the Road graph, Grid points and Routes;
  - the Flood-Prone Area;
  - Shelters and High-ground points;
  - the Weather Grid over the bbox;
  - every Event built into its Replay.

  Nepal's country border and district layers are Nepal-only work and are deleted. Nepal gets the same generic basemap.
- **Built-in Regions' packs are published as GitHub Releases** tagged `cache-pack-<region>-v<N>`. A Node downloads the pack for its Region from the Release while online and keeps today's rule never to re-download a valid pack. `CACHE_PACK_URL` still overrides the source.
- **A Region is chosen by `NODE_REGION`** (default `fort-myers`) on a Hub, and by the Region picker in the Sandbox. A Sensor Node takes the Region from the Hub's pack.
- **The Event clock tag and alert times use the Region's time zone.** The fixed Nepal offset and "NPT" go, and the label comes from the zone ("EDT", "NPT").
- **The Official Alert source becomes the Region's.** The fixed `dhm | ndrrma | district` list gives way to the source names in the Region file. The Official Alert message stays under the packet cap.
- **Official Gauges are a new Hub message** (agency, station, level in the wire unit and datum, observed time), trusted only from the Hub like Shelter status.
  - While online, the Hub polls each of the Region's gauges (NOAA CO-OPS latest water level, about every 6 minutes) and publishes the level over the Mesh.
  - During a Replay, the gauge's recorded series plays on the Event clock instead, labelled REPLAY.
  - Official Gauges are shown with their own marker and never enter Flood Risk, Surge or a Community Warning.
- **Live NWS alerts are out of scope.** A Region's Official Alerts come from its Events' Replays only (see Out of Scope).

### 3. The coast model

- **Ground height comes from the pack's terrain tiles.** For Florida those are USGS 3DEP heights in metres above NAVD88. Ground heights are approximate: coastal terrain is off by tens of centimetres, and the map and the Water ETA say "about".
- **One datum per Region.** The build converts every gauge series to the Region's datum with the station's published datum offset (Fort Myers 8725520 is recorded in ft above MHHW). Sensors, the Replay surface and ground heights all compare in that datum.
- **The Flood-Prone Area on a coast is the land below `flood_prone_below`.** The build traces it from the terrain inside the bbox as polygons, and the map marks it approximate. A river Region keeps its hand-drawn corridor.
- **Water ETA on a coast is worked out on the Viewer, never on the Hub.**
  - Inputs: the home's ground height (read from the pack's terrain on the device), the latest `water_level` from the nearest counting Node that reports one, and that Node's rate of rise over the Region's `rising_window_s`.
  - The ETA is (ground height − level) ÷ rate, counted down on the Event clock. It is shown in hours and minutes ("Water reaches your ground in about 2 h 10 min") with its basis ("level 5.1 ft, rising 1.4 ft/h, your ground 8.2 ft").
  - It reads "Water is at your ground now" once the level reaches the ground.
  - There is none while no counting Node reports a rising level, or while the home is above every level the Rule set's High threshold implies.
  - It is re-judged as each reading arrives, so it moves with the rate of rise. The Reachable Shelter rule uses it unchanged: walking time less than the Water ETA minus the safety margin.
- **The river Water ETA is unchanged** (Surge arrival at the home snapped to the river line). The dashboard picks one or the other by the Region's water type.

### 4. Events and Replays

- **An Event file describes one Event at one Region**: id, label, Hazard, real or made up, the window (start and end in the Region's time zone), default rate, named phases, the internet cue, Official Alerts with their times, and the water surface and weather.
  - Real Events are generated by the build from the Region's sources.
  - Made-up Events are hand-written in `regions/<name>/events/`.
  - Both end up in the pack in the same shape. Trimmed shape:

  ```json
  { "id": "ian-2022", "label": "Hurricane Ian storm surge", "hazard": "storm_surge", "real": true,
    "start": "2022-09-28T06:00", "end": "2022-09-28T21:00", "rate": 30,
    "phases": [{"id": "landfall", "label": "Landfall at Cayo Costa", "at": "2022-09-28T15:05"}],
    "surface": { "datum": "NAVD88", "unit": "m", "stations": [
      {"id": "fmb-pier", "label": "Fort Myers Beach Pier", "pos": [26.4507, -81.9533],
       "reconstructed": true, "series": [[0, 0.62], [360, 0.66]]} ] },
    "weather": "weather_grid",
    "official_alerts": [{"at": "...", "source": "nws-tbw", "headline": "Storm Surge Warning"}] }
  ```

- **The water surface** is a set of stations, each with a level series (seconds from the Event start against level).
  - On a coast, the level at a spot is the inverse-distance blend of the stations at that moment. The spot is wet when that level is above its ground height.
  - On a river, the stations sit at River kms. The level at a spot inside the corridor is interpolated along River km; outside the corridor the spot is dry.
- **Each Sensor reads its Simulated Readings from the surface at its own true position** (the position is fuzzed only on publish).
  - `water_level` is sent when the spot is wet.
  - `rain_rate`, `soil_moisture` and `air_pressure` come from the Event's weather at that spot. The weather is the Weather Grid recorded over the Event's window for a real Event, or a few hand-written keyframes applied evenly for a made-up one.
  - With the Event clock stopped, a simulated Sensor reads the first moment of the loaded Event. That replaces the Scenario's "normal day".
- **The Event clock, its Mesh message and its controls are kept** (play, pause, reset, jump to phase, rate). They gain an Event id, so every Node plays the same Event, and the Replay controls gain an Event picker. Replay tracks pinned to named Nodes (`NODE_REPLAY_TRACK`) go: any Sensor anywhere reads the surface.
- **The Hazard picks the Community Warning's trigger and title.**
  - `flash_flood`: a Surge (`surge_rise` within `surge_window_s`) on a Registered Node, as today. Titled "Flash Flood".
  - `storm_surge`: a Registered Node's `water_level` passes `warning_height` while it has risen at least `rising` over `rising_window_s`. Titled "Storm Surge". It carries the Node, its level, its rate of rise and the time; each Viewer then works out its own Water ETA.

  Either way the Hub issues one warning per Node and Hazard while the condition holds, as today. The word "Surge" is never shown alone on screen.
- **Official Alerts in an Event appear at their real times on the Event clock**, as today.

### 5. The Fort Myers Region and the Ian Replay

- **Bounds**: Fort Myers Beach and Estero Bay, from downtown Fort Myers to Bonita Springs, about 26.30 to 26.67 N and 82.00 to 81.75 W. The first Region ticket sets the exact box. Time zone `America/New_York`; display units ft, in/h, inHg and mi; datum NAVD88.
- **Water**:
  - The Fort Myers gauge (NOAA 8725520, 6-minute verified water level, 26 to 30 Sep 2022, peak 7.257 ft MHHW at 22:30 UTC on 28 Sep) is one station.
  - Estero Bay and Fort Myers Beach are stations whose series is the Fort Myers curve scaled to NHC's 12.7 ft MHHW peak at Fort Myers Beach Pier. They are marked `reconstructed`, and the Replay says so on screen.
  - The scaling doesn't move the curve in time, so the beach's peak plays at the Fort Myers gauge's peak time. That's a known error the USGS readings will fix.
  - When the USGS storm sensor readings arrive (instrument ids 10768, 10773, 10747, 10855, 10854, 10861), they replace the scaled stations and the `reconstructed` label comes off. Neither the Naples gauge nor the predicted tide is used.
- **Official Alerts**:
  - They come from the NWS Tampa Bay (TBW) warnings file: rows for Lee County zones FLZ165 (coastal) and FLZ265 (inland) that are issued or upgraded inside the Event window.
  - Phenomena kept: storm surge, hurricane, tropical storm, flood and flash flood, both watches and warnings.
  - Each row becomes an Official Alert headed by its phenomenon and significance ("Storm Surge Warning") at its `utc_issue` time, shown in Eastern time.
- **Official Gauges**: the Region lists the NOAA tide gauges inside the bbox, starting with 8725520. Live, the Hub brings them in while online. In the Ian Replay, 8725520's recorded series plays as a REPLAY Official Gauge.
- **Shelters** are hand-picked from Lee County's published shelter list into the Region file, each outside the Flood-Prone Area. **Suggested sensor sites** start from the USGS deployment sites for Ian in Lee County (Estero Bay at Coconut Point Marina and the others in the sources file).
- **Fort Myers is the default Region** for `NODE_REGION`, for the Sandbox and for the tests. Tests use a small checked-in fixture pack built from the Region file, so they never fetch anything.
- **Proxy note:** cloud agent sessions run behind a proxy that blocks NOAA (`tidesandcurrents.noaa.gov`, `api.tidesandcurrents.noaa.gov`) and USGS (`stn.wim.usgs.gov`, 3DEP hosts). The Fort Myers build, and live Official Gauges, need those hosts allowlisted in the environment's network policy, or a run on a laptop. The checked-in `sources/` files are what make the Ian Replay buildable without them; the build only re-fetches when asked.

### 6. The Sandbox

- **One command**, e.g. `uv run storm-shield-sandbox` (optionally `--region nepal`, `--port`), starts everything in one process:
  - a Hub and one simulated Sensor at each of the Region's suggested sensor sites, all on one shared in-memory Mesh;
  - the Hub's identity known in-process, so nothing is copied;
  - every Sensor registered through the normal signed registry (Sign-up and accept are done for the user);
  - the Region's pack from disk, or downloaded from its Release while online.

  It serves the Hub's dashboard on one port and opens it in the browser. No pack server, no loopback slots, no data dirs to choose: everything lives in a temporary folder that's removed on exit. A desktop launcher comes later (Out of Scope).
- **The in-memory Mesh gains a radio range.** Each Node has a true position. A message reaches every Node joined to its sender by a chain of Nodes each within range of the next, so it hops through Nodes.
  - The default range is 1 km. The tests' own harness can set "unlimited".
  - Hops are instant: the Sandbox models who hears, not radio delay.
  - Moving a Node or changing the range takes effect on the next message.
- **The Sandbox has a small HTTP API on its Hub**, only present in the Sandbox:
  - list Nodes, with each one's position, links, hop count to the Hub (or none) and whether it has heard the latest Community Warning;
  - add a Sensor at a position;
  - move a Sensor;
  - remove a Sensor;
  - set the radio range;
  - switch Region (restarts the in-process Mesh with the new Region's pack).

  Event picking and play use the normal Replay routes.
- **On the dashboard**, a Sandbox Panel (shown only when `/api/state` reports `sandbox`) holds:
  - the Region picker;
  - the radio range slider;
  - "Add Sensor", then tap the map;
  - the Node list with hop count and "heard warning" ticks;
  - the Event picker with play, pause, reset, rate and phases, and the Event clock beside them.

  On the map, Sensors are draggable, each Node has its range circle, links join Nodes in range, a Sensor with no path to the Hub is marked "no path to Hub", and suggested sensor sites show as faint markers that become Sensors on a tap.
- **The Sandbox is also the test harness.** `MeshedNodes` is rebuilt on the Sandbox module (the same in-process Hub, Sensors and in-memory Mesh with an injected clock), so the tests and the hand-run Sandbox share one code path.

### 7. Deletions

Each deletion takes its tests, docs and glossary entries with it in the same PR.

- **Simulated Fleet**:
  - Node: the fleet module, the `fleet` field in `/api/state`, the fleet pack script and its source file.
  - Dashboard: the fleet popover, the Fleet rail button and the "N simulated Nodes · M real" badge.
  - Glossary: Simulated Fleet and Headwater Node (its Fleet clause).
  - ADR 0005, point 2, is marked superseded.
- **Camera clips and the Cameras Panel**:
  - the camera list and camera routes;
  - the `camera-clips/` folder and its clip script;
  - the Cameras Panel and its fake media;
  - the demo script's clip lines;
  - the Nepal cameras research and the online-status-and-cameras spec's camera half;
  - glossary: Camera and Camera Clip.

  Cameras return as sensors in M6.
- **Breadboard and Scenario**:
  - the Scenario and breadboard modules, the GPIO setting and the Scenario routes;
  - the Node Panel's Scenario controls (the Node Panel keeps the registration status);
  - the breadboard spec and the Pi pin table;
  - the `pi` dependency group and its lessons lines, if nothing else uses `lgpio`;
  - glossary: Scenario and Breadboard.

  Tests that built readings with the Scenario build them by hand or from a made-up Event instead. The Audience Node's readings come from the Replay surface at its position.
- **Nepal**:
  - What moves mechanically stays as the `nepal` Region: its bbox, time zone, metric units, river line and River km, corridor, Shelters, High-ground points, today's thresholds, and the Bhote Koshi Replay. Its four tracks become four River km stations, and its DHM alerts move into its Event file.
  - Anything that needs real Nepal work is deleted: the country border and district layers, the whole-of-Nepal Weather Grid (the Region's bbox replaces it) and Nepal-specific map styling.
  - If the river surface turns out not to be mechanical, the Bhote Koshi Replay is deleted too and Nepal stays a map-only Region.
  - The `v0-swamphacks` tag keeps the original.

### 8. The look stays swappable

The mock-ups for issue #21 settled what the screens hold and how they behave, not how they look. The owner doesn't like the current look: the colours, the sharp corners, and a coast that looks blocky instead of fluid and real. A redesign is expected later, so nothing built here may lock the look in.

- **Every visual value is a theme role in `theme.css`.** That covers colours, corner radii, shadows, fonts and motion. The new screens need new roles: the range circle, a link, "no path to Hub", a Sensor being dragged, the Official Gauge marker, the coast Water ETA. Components use roles only, as `theme.test.ts` already enforces for colours, so a new look means editing one file.
- **The map draws the Region's real geography.** The coastline, water and land come from the Region's basemap data (OpenStreetMap) at its true shape. Nothing is hand-drawn or approximated as blocks. Fills, line widths and opacities live in one map style module that reads theme roles, so the map can be restyled without touching map logic.
- **Placement belongs to the layout stylesheet, not the components.** The Sandbox, Region picker and Evacuation Plan pieces are built from the existing Panel and its parts, and where each one sits is set in CSS. Panels can be moved around without rewriting them.
- **No ticket here polishes the look.** Each ticket builds the behaviour with today's theme, and a later design pass re-themes it.

### 9. Milestones

- **M3 Sandbox**:
  - the generic Measurements wire change and its two tests (first, per ADR 0006);
  - the deletions;
  - the Sandbox command, the in-memory Mesh with radio range and hops, and `MeshedNodes` on the Sandbox;
  - the Sandbox Panel (place, drag and remove Sensors, range slider, circles and links);
  - Events picked and played from the dashboard, on the existing Nepal Replay converted to a river surface.
- **M4 Regions**:
  - the Region file and its schema, with thresholds read from it;
  - the one build command and the generic basemap;
  - Releases per Region and `NODE_REGION`;
  - Nepal moved behind the Region file;
  - the Fort Myers Region (bbox, Shelters, sensor sites, coast Flood-Prone Area), the default and the tests' Region;
  - the Region picker; time zone and display units on screen.
- **M5 Event on any Region**:
  - the coast surface;
  - the storm-surge Hazard trigger and title;
  - the coast Water ETA in the Evacuation Plan;
  - the Ian Replay with its NWS Official Alerts;
  - Official Gauges (live and replayed);
  - made-up Event files for both Regions.
- **M6 General sensors** (the end goal):
  - Sensor Nodes declaring kinds beyond the flood four;
  - a second Rule set when one is needed;
  - cameras back as sensors;
  - the desktop launcher.

`docs/roadmap.md` is updated to match.

## Testing Decisions

- **A good test drives the app from outside and checks what a person or another Node would see**: the HTTP API of a Node, the dashboard as rendered, or the files the build writes. It never checks a module's internals, and it reads its numbers from the Region file, so a threshold change doesn't break it.
- **The Node's test seam is the Sandbox.** A test starts the Sandbox with the Fort Myers fixture pack, places Sensors, plays or advances an Event (or hands a Sensor its readings), and asserts on `/api/state`, the Community Warning log and the Sandbox API. `MeshedNodes` becomes a thin pytest fixture over it. Prior art: `meshed_nodes.py` with its injected clock and `test_replay_drives_the_sensor_nodes.py`.
- **Tests that come out of this work**:
  - Wire format: a version 2 reading carries only the declared kinds, stays under the size bound and comes back unchanged.
  - An unknown kind is shown and never counted.
  - Thresholds come from the Region: changing the fixture Region's `warning_height` moves when the storm-surge warning fires.
  - Radio range: a Sensor out of range of everyone is never heard by the Hub; it is heard through a relay Node in range of both; dragging it into range makes it heard; shrinking the range cuts it off.
  - Coast Replay: a Sensor at the bay shore reports a `water_level` and one inland on higher ground reports none; the storm-surge Community Warning fires when a Registered shore Sensor passes the warning height while rising.
  - Official Gauges show in `/api/state` and never change Flood Risk.
  - Official Alerts from the Ian file appear at their Event clock times.
  - The Sandbox's "heard the warning" is false for a Node with no path to the Hub.
- **The dashboard seam is the existing Vitest flow tests** with `fakeNodeState()`, extended with a fake Sandbox state and Region. Prior art: `evacuationFlow.test.tsx`, `replayControlsFlow.test.tsx`, `layerRailFlow.test.tsx`, `packOnMapFlow.test.tsx`. Tests:
  - The coast Water ETA line ("Water reaches your ground in about 2 h 10 min") for a home, its ground height, a level and a rate.
  - "Water is at your ground now".
  - No Water ETA while the level falls.
  - Feet and miles shown for Fort Myers.
  - The Region's time zone on the Event clock tag.
  - The Sandbox Panel's controls send the right Sandbox calls; range circles and links read back from the fake map with `sourceData`.
- **The build's seam is the build command run on a tiny fixture Region** whose sources are local files, asserting the pack's contents: the Region file inside it, the Flood-Prone Area polygons below the set height, the Event surface in the Region's datum, and the Official Alerts filtered to FLZ165 and FLZ265. Prior art: the `test_pack_*.py` tests. Nothing in CI fetches from the network.
- **Deleted features' tests are deleted with them, not fixed.** The two exact-field tests are rewritten, not loosened.
- **Nothing here is proven on a Pi or a sensor.** The radio range is a model; LoRa and real radios are untested (AGENTS.md, "No Pis or sensors").

## Out of Scope

- A desktop launcher or a "start Sandbox" button outside a terminal (M6).
- Live NWS alerts from the NWS API. Official Alerts come from Event Replays only for now. Live NOAA tide gauges as Official Gauges are in scope.
- A rule engine, plugin points or any second Rule set (M6).
- Cameras of any kind until they return as sensors (M6).
- Real sensors, real radios, LoRa, radio delay or packet loss in the range model.
- New Nepal work: new layers, new data, a live DHM feed. Nepal stays only where moving it is mechanical.
- Separating surge from tide; the Replay uses total water level.
- The Naples gauge.
- Viewing the dashboard "as" a particular simulated Sensor; the Sandbox's Node list stands in for it.
- A hosted service of any kind.

## Further Notes

- The open item from issue #21 (the USGS storm sensor readings for Fort Myers Beach and Estero Bay) doesn't block this spec. The Ian Replay ships with the scaled, labelled-reconstructed stations and swaps them when the readings are fetched from a laptop.
- Mock-ups: https://claude.ai/artifact/AjDsPvQPY3DFkSp1qzVCTH (Sandbox controls, Region picker, coast Water ETA). They were approved for content and behaviour only; see decision 8 for the look.
- The Fort Myers thresholds in the Region-file example are placeholders. The ticket that writes the Region file sets them from the NWS storm-surge categories and records where they came from.
- Glossary entries that this work makes untrue go in the PR that makes them untrue. Scenario, Camera, Camera Clip, Simulated Fleet and Breadboard go with their deletions. River km becomes a river-Region term. Shelter's "well above the river" becomes "outside the Flood-Prone Area". The God's Eye View's "whole of Nepal" becomes "the whole Region".
- `docs/specs/wire-formats.md` is updated in the wire-format PR. Its "units in the field names" rule becomes "units in the Measurement".
