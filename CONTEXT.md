# Storm Shield

A community flood warning dashboard, demonstrated on a replay of the 26 August 2026 flood down the Bhote Koshi and Trishuli in Nepal (ADR 0004). Community sensor readings are shared over a local mesh, so a surge seen upstream warns the towns downstream, and residents keep their warning and evacuation plan when the internet goes down. It adds local ground truth next to official information (DHM, NDRRMA, district offices); it never replaces it.

## Network

**Mesh**:
The set of Nodes that reach each other peer to peer, directly or through one another, with no internet needed.
_Avoid_: network, cloud, backend

**Node**:
Any device taking part in the Mesh.
_Avoid_: peer, device, client

**Node id**:
The 12-character code taken from a Node's permanent Reticulum identity; it is how Nodes, the registry and the API refer to a Node.
_Avoid_: identity, address, hash

**Node name**:
The label an operator gives a Node, such as "garage"; it is shown to people and never used to tell Nodes apart.
_Avoid_: id, username

**Sensor Node**:
A Node that produces Community Readings from attached or simulated sensors.
_Avoid_: station, sensor box

**Registered Node**:
A Node whose Node id the Hub has accepted at sign-up; only its Community Readings count toward Flood Risk and Community Warnings.
_Avoid_: trusted node, verified device

**Unverified Node**:
A Node the Hub does not know; its readings are shown but never counted.
_Avoid_: rogue node, guest

**Sign-up**:
A Node's signed request, sent over the Mesh, to be added to the Node registry under its Node name; it waits until the Hub operator accepts it.
_Avoid_: enrolment, pairing, join request

**Node registry**:
The Hub's signed list of Registered Nodes (Node id and Node name), always including the Hub itself; with no registry received yet, no Node counts.
_Avoid_: allowlist, roster, trust list

**Hub**:
The one Node that collects every Community Reading, issues Community Warnings and hosts the central dashboard; when it has internet it also brings Official Alerts and the Cache Pack into the Mesh.
_Avoid_: gateway, central server, cloud, backend

**Dial address**:
The `host:port` another Node can dial to reach this Node over TCP; Nodes share the ones they know in their announces, so one known address is enough to find the rest.
_Avoid_: peer address, endpoint, IP

**Hub takeover**:
Starting a standby Node as the Hub with a copy of the Hub's key, after the Hub has stopped; it carries on from the last Node registry and Shelter status the Mesh heard.
_Avoid_: failover, election, backup hub

**Mesh-only**:
A Node that currently has no internet and still takes part in the Mesh. Each Node reports only its own state: Online or Mesh-only. Online-only features (live feeds) stop while a Node is Mesh-only; everything carried over the Mesh keeps working.
_Avoid_: offline node

**Viewer**:
A phone or browser that shows the dashboard by connecting to a Node, without being part of the Mesh itself.
_Avoid_: client, user device

**Sandbox**:
A Hub and any number of simulated Sensor Nodes started by one command in one process, sharing an in-memory Mesh, for the team to try the app without a terminal juggling ports, slots and Hub ids. Sensors are placed on the map and the event is played from the dashboard. A message reaches only Nodes within a set radio range, directly or hopping through other Nodes. Every reading in it is a Simulated Reading.
_Avoid_: simulator, demo mode, playground

## Information

**Community Reading**:
One timestamped set of Measurements from a Sensor Node.
_Avoid_: data point, sample, telemetry

**Measurement**:
One value in a Community Reading with its kind and unit, such as water level in m or air pressure in hPa. A Sensor Node declares the kinds it measures; nothing in the Mesh assumes a fixed list.
_Avoid_: field, metric, value

**Rule set**:
The rules that turn the Measurements a Node can see into states and warnings. Flood warning (Flood Risk, Surges, Community Warnings) is the first and, for now, only Rule set; others follow as Storm Shield grows into a general sensor network.
_Avoid_: plugin, module, detector

**Simulated Reading**:
A Community Reading whose value comes from an Event's replayed surface instead of a real sensor; always labeled as such.
_Avoid_: fake reading, mock data

**Fuzzed Position**:
A Node's location snapped to a grid of about 200 m before anything is published; the true location never leaves the Node. A fixed grid, not random jitter, because jitter can be averaged away by an observer collecting many readings.
_Avoid_: exact location, coordinates

**Event**:
One happening at a Region, of one Hazard: Hurricane Ian's storm surge at Fort Myers on 28 September 2022, or the Bhote Koshi flash flood of 26 August 2026. An Event can be real or made up for testing. It is described by an Event file: id, window, rate, named phases, internet cue, Official Alerts with their times, the water surface and the weather.
_Avoid_: scenario, incident, storm (alone)

**Hazard**:
The kind of Event: flash flood or storm surge today, others (lightning, frost) as more Rule sets arrive. The Hazard names the Community Warning and decides what triggers it.
_Avoid_: event type, threat, disaster

**Replay**:
How an Event is played: a file describing the water surface and weather over time, played on the Event clock. The surface is a set of stations, each a level series; on a river they sit at River kms, and a Sensor Node inside the corridor reads the level interpolated along River km, while one outside it is dry and sends no water level. Each Sensor Node reads its Simulated Readings at its own position, so a Node on high ground stays dry; a real Event's Replay is rebuilt from recorded gauges and reports, and its Official Alerts appear at their real times. Always labelled REPLAY. A Replay is for checking the system and for demos: a Region runs either on live readings or on one of its own Replays, never both on one map, and never another Region's Replay.
_Avoid_: playback, recording, simulation

**Event clock**:
The time inside the Event being played (for example 28 Sep 2022 · 14:06 EDT), run by the Hub and followed by every Node, whose message carries the Event's id so all play the same Event; it moves ×30 faster than real time and can be paused or jumped to a named phase.
_Avoid_: replay time, sim time

**River km**:
A river-Region term: a Node's or home's distance along the river from the Region's origin (the Lhende–Kyirong confluence at the border in Nepal), positive downstream; set in each Node's config and measured on the river line in the Cache Pack. A coast Region has no river line, so its Nodes have none.
_Avoid_: chainage, mile marker, distance

**Water ETA**:
How long until flood water reaches a Viewer's home, counted down on the Event clock and worked out on the Viewer (never on the Hub; the home never leaves the device). On a river, it is when the Surge in a Community Warning arrives at the home snapped to the river line; with several warnings it follows the earliest, and a home upstream of the origin or more than 2 km from the river line has none. On a coast, it is when the rising water level reported over the Mesh passes the home's ground height, at its current rate of rise.
_Avoid_: Wave ETA, countdown, arrival time, ETA (alone)

**Measured wave speed**:
The speed of a Surge between the first two Registered Nodes that surged, worked out by the Hub from their River kms and Surge times and carried on the Community Warning; it replaces the reconstructed speed for the reaches below the second Node.
_Avoid_: actual speed, live speed

**Official Alert**:
A warning or order issued by one of the Region's official alert sources, named in its file (DHM, NDRRMA or a district office in Nepal; the National Weather Service in Florida), shown distinctly from community information.
_Avoid_: warning, notification

**Official Gauge**:
A government water-level station (a NOAA tide gauge in Florida) whose measurements the Hub brings into the Mesh while online. Shown beside Community Readings and visibly different from them; never counted toward Flood Risk.
_Avoid_: official sensor, station, buoy

**Community Warning**:
A signed warning the Hub issues when one Registered Node reports a Surge; it names that Node and its River km so each Viewer can work out when the wave reaches its home. Never an evacuation order, and always points residents to official sources for evacuation decisions.
_Avoid_: alert, alarm, evacuation notice

**Region**:
The place a Storm Shield network watches, described in one small hand-written file: its name, area, time zone, display units, official alert source, the water it watches (river or coast), the thresholds its Rule set uses, its Shelters and its suggested sensor sites. Adding a region means writing this file, not code. Nepal's Bhote Koshi valley is one Region; a Florida coast is the second.
_Avoid_: map, area, location, scenario

**Cache Pack**:
The bundle of offline information (the Region file, an OpenStreetMap basemap, terrain, Shelters, Flood-Prone Areas, Routes, the Weather Grid and Event files) built from a Region's file by `scripts/build-cache-pack.sh <region>`, then downloaded by every Node while online and served from its own disk so it works without internet. The Hub gets its Region's pack from the GitHub Release `cache-pack-<region>-v<N>` (or from `CACHE_PACK_URL`, such as a laptop serving the zip); sensor Nodes get it from the Hub.
_Avoid_: offline data, bundle, snapshot

**Flood Risk**:
A community estimate of flooding danger (Low, Elevated or High) that every Node derives from the Community Readings it can see. Low is shown only while it is Raining or the Storm Signal is on. Elevated and High come from a Node's own water level and rain rate, so water at 300 cm or more shows Elevated even on a calm day. With none of these, no Flood Risk is shown at all.
_Avoid_: flood score, danger level, threat level

**Raining**:
The condition, judged across the Mesh and not from any single Node, that soil moisture is rising at two or more of the Nodes that count (or at the only one that counts). It is what lets Flood Risk appear as Low.
_Avoid_: wet weather, precipitation

**Surge**:
A sudden rise in one Node's water level, at least a set amount within a short window: the flash-flood trigger. It makes that Node's Flood Risk High at once and triggers a Community Warning titled with the Hazard; the word itself is never shown alone on screen.
_Avoid_: storm surge (that is a Hazard), spike, flash, wave

**Storm Signal**:
The dashboard indicator that air pressure is low across the Nodes that count, a sign a storm is approaching. It stays on while pressure stays low and is separate from Flood Risk, though it makes Flood Risk appear (as Low) when nothing else would.
_Avoid_: storm warning, storm alert, pressure alarm

## Evacuation

**Evacuation Plan**:
What a resident should do and where to go: their risk, and either the nearest open Shelter they can walk to before the wave or, if there is none, higher ground away from the river. Their risk is the Mesh-wide Flood Risk (the worst level across the Nodes that count), not a level tied to where their home is.
_Avoid_: evac info, escape route

**Reachable Shelter**:
An open Shelter that fits the household, lies outside the Flood-Prone Area, and can be walked to before the wave: its walking time is less than the Water ETA minus a safety margin. Re-judged every second on the Event clock; with none, the Evacuation Plan says to get to higher ground.
_Avoid_: safe Shelter, nearest Shelter (the nearest need not be reachable)

**Household Profile**:
A resident's home location, housing type (site-built or mobile home/RV), and whether they need a special-needs or pet-friendly Shelter; kept only on their own device. The one thing it reveals is the Grid point nearest home, when the Viewer asks its connected Node for the Route; never to the rest of the Mesh.
_Avoid_: user profile, account, settings

**Route**:
The driving path from a Grid point to a Shelter, precomputed into the Cache Pack. It is the shortest drive and ignores Flood-Prone Areas and live road conditions; its length ranks Shelters. When it crosses a Blocked Road or a Flood-Prone Area, the phone replaces it with one computed on the device. A Shelter with no Route from the resident's Grid point ranks after every Shelter that has one, by straight-line distance and labelled as such, with no line drawn.
_Avoid_: directions, navigation, path

**Blocked Road**:
A road segment a resident marked as impassable by tapping the map; kept only on their own device, never sent over the Mesh. The Evacuation Plan reroutes around it from the Road graph, so the Route is then computed on the phone from the actual home rather than read from the Cache Pack.
_Avoid_: closure, roadblock, obstruction

**Road graph**:
The drivable roads of the Cache Pack area as junctions joined by segments with their length, a file in the pack. Rerouting runs on it; it is separate from Routes, which are precomputed lines.
_Avoid_: road network, map data

**Grid point**:
One of the evenly spaced points, about 100 m apart, that cover the roads of the Cache Pack area; a home takes the Route of its nearest Grid point. Areas more than about 100 m from a drivable road have none.
_Avoid_: waypoint, cell, node

**Shelter**:
A public building outside the Flood-Prone Area, picked by hand into the Cache Pack (the build refuses one inside it), where people can wait out a flood.
_Avoid_: refuge, safe place

**Shelter status**:
Whether a Shelter is open or closed, set by the Hub operator and announced over the Mesh; a Shelter counts as open only once the Hub has announced it.
_Avoid_: availability, capacity

**High-ground point**:
A hand-placed spot on the hillside above a town, picked into the Cache Pack with its climb above the river. It is not a Shelter: never open or closed, never ranked by Route. The map shows the points only while the Evacuation Plan says to get to higher ground, with no Reachable Shelter.
_Avoid_: safe zone, refuge

**Flood-Prone Area**:
The land the Region's water can reach: on a river, the corridor drawn by hand along it (the Lhende Khola, Bhote Koshi and Trishuli in Nepal); on a coast, the land below a set height, which the Cache Pack build traces from the terrain. A Shelter inside it is never offered. The map always marks it approximate.
_Avoid_: evacuation zone, surge zone

## Dashboard

**Real Node**:
A Node that is actually on the Mesh (the Hub, the Pi, an Audience Node), as opposed to a simulated one. Shown with the `REAL` ring.
_Avoid_: physical node, live node

**Audience Node**:
A Registered Node on a volunteer's laptop, started with `scripts/join-demo.sh`. It is a Real Node on the real Mesh, but its readings come from the Event's surface, so they are simulated.
_Avoid_: guest node, visitor node, demo laptop

**God's Eye View**:
The desktop dashboard's map of the whole Region, drawn from the basemap and terrain in the Cache Pack with slight 3D terrain: every Node glowing on it and the flood wave visibly running down the river. Made for the projector and judges' laptops; the phone layout is separate.
_Avoid_: globe, surveillance map, overview

**Headwater Node**:
A Node placed where a flood starts (a glacial lake outlet, a glacier front, an upper valley), so its Surge is the earliest sign for the towns downstream. S0 is the Replay's Headwater Node.
_Avoid_: sentinel, upstream sensor, enthusiast node

**Contact lost**:
The cue on a Node's marker when it has been silent for about 5 seconds: its glow dies and a ring counts down to Stale at 15 seconds. Display only; it changes no Flood Risk or Surge rule.
_Avoid_: disconnected, dropped, offline node

**Warning Takeover**:
The modal that interrupts any view when a new Official Alert or Community Warning arrives, with one large acknowledge button; it fills a phone's screen and floats over the dimmed map on a larger one. Acknowledging it on one device never clears it on another.
_Avoid_: popup, alarm, klaxon, notification

**Stale**:
A Node whose last Community Reading arrived more than 15 seconds ago by the receiving Node's own clock; after 60 seconds its readings stop counting toward Flood Risk. The age is shown on the Node's map marker and Node card.
_Avoid_: offline node, dead node, timed out

**Node unreachable**:
The dashboard's state when a Viewer gets no answer from the Node it is connected to. It is about the Viewer's link to its own Node, not the Mesh: a Node can be Mesh-only or have Stale peers and still be reachable. While it lasts, live readings, Flood Risk and online status are not shown; what is already on the Viewer's device (the Cache Pack, the Household Profile) stays.
_Avoid_: offline, disconnected, down

**Layer rail**:
The column of buttons along the left edge of the dashboard that shows and hides map layers and Panels, each with a live count where one applies.
_Avoid_: sidebar, toolbar, nav

**Weather layer**:
One of Temperature, Cloud cover or Rain, laid over the map's terrain from a Weather Grid; only one shows at a time, chosen from the Weather button on the Layer rail. It is context for the country and the valley, never a measurement at a village and never offered as a cause of the flood.
_Avoid_: overlay, weather widget, radar

**Weather Grid**:
Hourly temperature, cloud cover and rain on a coarse grid of points (about 0.5° apart) over the Region's bounding box. During the Replay it is the recorded weather around the Event, built into the Cache Pack; otherwise it is the Hub's last good forecast, shown with its age.
_Avoid_: weather data, forecast feed

**Panel**:
A translucent box floating over the map that holds one kind of information (Readings, Alerts, Evacuation Plan) and can be collapsed without leaving the map.
_Avoid_: widget, sidebar, column

**Node card**:
One Node's entry in the Readings Panel: its name, tags, water level and the other Community Readings with their trends.
_Avoid_: tile, row, sensor card

**Hub Panel**:
The slide-over on the Hub's dashboard holding the Node registry, the Community Warning log, Shelter status and the Replay controls.
_Avoid_: admin page, settings, control panel

**Node Panel**:
The slide-over shown only on a Node's own screen, holding that Node's registration status; never shown to Viewers on other devices.
_Avoid_: operator panel, settings, admin

**Join card**:
The card with the two codes a phone scans to join the neighborhood Wi-Fi and then open the dashboard.
_Avoid_: QR, invite, onboarding
