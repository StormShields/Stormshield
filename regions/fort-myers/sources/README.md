# Fort Myers sources for the Hurricane Ian Replay

Raw inputs for the Ian Replay of the Fort Myers Region (issue #21). All are US government data, public domain.

| File | What | From |
|---|---|---|
| `noaa-8725520-fort-myers-water-level.csv` | Fort Myers tide gauge, 6-minute verified water level, ft above MHHW, UTC, 26–30 Sep 2022. Peak 7.257 ft at 2022-09-28 22:30. | NOAA CO-OPS `datagetter`, `station=8725520&product=water_level&datum=MHHW&units=english&time_zone=gmt` |
| `nws-tbw-warnings-2022-09.csv` | Every NWS watch and warning from the Tampa Bay office (TBW), 20–30 Sep 2022. Lee County is zones FLZ165 (coastal) and FLZ265 (inland). | Iowa Environmental Mesonet watch/warning download, filtered to `wfo == TBW` |
| `usgs-stn-ian-sensors-lee-collier.csv` | Where USGS deployed storm sensors for Ian in Lee and Collier counties, with instrument ids. Positions only, no readings. | USGS STN Flood Event Viewer, event "2022 Ian", filtered to Lee and Collier counties |

## The Ian Event built from them

`uv run --project node python scripts/pack_ian_event.py` reads these files (never the network) and writes `../events/ian-2022.json`, which the Cache Pack build carries. To refresh a source, download it again with the query in the table, replace the file and run the script; nothing else re-fetches them.

- **Water**: the Fort Myers gauge is one station (ft above MHHW plus the gauge's `datum_offset` in `region.json`, in metres above NAVD88). Fort Myers Beach Pier and Estero Bay are the same curve multiplied to NHC's 12.7 ft above MHHW peak, marked `reconstructed`; the Replay says so on screen.
- **Known timing error**: the scaling does not move the curve in time, so the beach's peak plays at the Fort Myers gauge's peak time (22:30 UTC). The real beach peak came earlier; the USGS readings will fix it.
- **Official Alerts**: the TBW rows for Lee County zones FLZ165 and FLZ265 with phenomena storm surge, hurricane, tropical storm, flood, areal flood and flash flood (watches and warnings) that are in force during the 06:00 to 21:00 Eastern window. Ian's were all issued on 26 and 27 Sep, before the window, so they show when the Replay starts, each with its own issue time; the two zones' rows for one notice make one alert.
- **Weather**: the Weather Grid plays over the window on the map. It holds no soil moisture or pressure, so a Sensor's rain, soil and pressure follow hand-set keyframes in the script, not measurements.

Not used: the Naples gauge (8725110), which failed before the peak, and the predicted tide, because homes flood on total water level. Still missing: the USGS sensor readings. Until the readings are in, Estero Bay's water is the Fort Myers curve scaled to the 12.7 ft MHHW peak NHC reports at Fort Myers Beach Pier, and the Replay says so.
