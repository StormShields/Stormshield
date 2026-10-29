# Fort Myers sources for the Hurricane Ian Replay

Raw inputs for the Ian Replay of the Fort Myers Region (issue #21). All are US government data, public domain.

| File | What | From |
|---|---|---|
| `noaa-8725520-fort-myers-water-level.csv` | Fort Myers tide gauge, 6-minute verified water level, ft above MHHW, UTC, 26–30 Sep 2022. Peak 7.257 ft at 2022-09-28 22:30. | NOAA CO-OPS `datagetter`, `station=8725520&product=water_level&datum=MHHW&units=english&time_zone=gmt` |
| `nws-tbw-warnings-2022-09.csv` | Every NWS watch and warning from the Tampa Bay office (TBW), 20–30 Sep 2022. Lee County is zones FLZ165 (coastal) and FLZ265 (inland). | Iowa Environmental Mesonet watch/warning download, filtered to `wfo == TBW` |
| `usgs-stn-ian-sensors-lee-collier.csv` | Where USGS deployed storm sensors for Ian in Lee and Collier counties, with instrument ids. Positions only, no readings. | USGS STN Flood Event Viewer, event "2022 Ian", filtered to Lee and Collier counties |
| `usgs-stn-ian-water-level.csv` | Water level of six of those storm sensors, every 30 s, metres above NAVD88, UTC, 28 Sep 2022 09:55 to 29 Sep 01:05 (the replay window with a margin). Columns: `instrument_id`, `site_number`, `time_utc`, `water_level_m_navd88`. Credit: U.S. Geological Survey Short-Term Network (STN), processed water level by USGS Caribbean-Florida Water Science Center, public domain. | USGS STN web services, the "Processed water level" NetCDF file of each instrument (below) |

## The Ian Event built from them

`uv run --project node python scripts/pack_ian_event.py` reads these files (never the network) and writes `../events/ian-2022.json`, which the Cache Pack build carries. To refresh a source, download it again with the query in the table, replace the file and run the script; nothing else re-fetches them.

- **Water**: the Fort Myers gauge is one station (ft above MHHW plus the gauge's `datum_offset` in `region.json`, in metres above NAVD88). The six USGS storm sensors are the other stations, at their deployment sites: Fort Myers Beach Pier (10768), Matanzas Pass (10773), Big Carlos Pass at Lovers Key (10747), Estero Bay at Coconut Point Marina (10855), San Carlos Bay at Punta Rassa (10854) and Mullock Creek (10861). Their files already give metres above NAVD88, the Region's datum, so nothing is added. Every 30 s reading in the window is kept, because the readings swing with a period near the 6-minute filter and thinning them misses the peaks. The beach peaks at 4.03 m at 18:39 UTC, hours before the gauge's 22:30. A sensor that started recording after 06:00 Eastern holds its first reading until it starts (Matanzas Pass, Big Carlos Pass and Estero Bay from about 07:30).
- **Official Alerts**: the TBW rows for Lee County zones FLZ165 and FLZ265 with phenomena storm surge, hurricane, tropical storm, flood, areal flood and flash flood (watches and warnings) that are in force during the 06:00 to 21:00 Eastern window. Ian's were all issued on 26 and 27 Sep, before the window, so they show when the Replay starts, each with its own issue time; the two zones' rows for one notice make one alert.
- **Weather**: the Weather Grid plays over the window on the map. It holds no soil moisture or pressure, so a Sensor's rain, soil and pressure follow hand-set keyframes in the script, not measurements.

Not used: the Naples gauge (8725110), which failed before the peak, and the predicted tide, because homes flood on total water level.

## Fetching the USGS readings again

`stn.wim.usgs.gov` now redirects to `apps.usgs.gov/stnweb`; the data comes from `https://api.waterdata.usgs.gov/stnservices/` (a GET needs no key). For each instrument id: `files/?sensor=<id>` lists its files; the one with `filetype` 2 and a description starting "Processed water level" or "Computed water level" (not "Raw sea pressure") is the NetCDF file, downloaded from `files/<file id>/item/`. File ids used: 130763 (10768), 130798 (10773), 130439 (10747), 130448 (10855), 131871 (10854), 131494 (10861). Read the variable `water_surface_height_above_reference_datum` (metres, NAVD88) against `time` (ms since 1970, UTC) with netCDF4, which is not a dependency of the repo; write the rows in the window to the CSV.
