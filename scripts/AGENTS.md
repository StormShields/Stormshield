# Lessons: Data builds

Area gotchas that are still true. Claude Code loads this file (through `CLAUDE.md`) only once a session reads a file in this folder; other agents read the nearest `AGENTS.md`. Add a line when something here breaks, surprises you or takes more than one try; delete a line once your change makes it untrue. Repo-wide lessons: `docs/agents/lessons.md`.

- **External sources are flaky; retry, don't conclude.** FEMA and Overpass reset or answer 502 at random; Overpass and Wikimedia need a `User-Agent`; Wikimedia answers 429 to bursts.
- **Open-Meteo answers with its own grid coordinates** and returns a dict for one point, a list for several.
- **A Region's sources are an address or a file under its folder** (`pack_sources.read_source`), so a build test points them at local files and a `MockTransport` that refuses every request proves nothing was fetched. `load_roads` needs `pyrosm`, so tests replace it with a small `Roads`.
- **OSM names differ from the ones residents read** (Syabrubesi is `Shyaphru` there, and Trishuli has no place node), so a High-ground point carries its own `town` and `town_pos` in the Region file and is never looked up in the basemap.
- **Overpass answers 502 at random on the first try**; the retry covers it. A saved Overpass answer (`out geom tags`) works as the basemap source.
- **Before committing footage, read the file's wikitext licence**, not only the API's short name. CC BY-SA and NC are out.
- **Walking time is straight line x 1.4 at 4 km/h, rounded up, in two places** (`pack_high_ground.py`, `evacuationPlan.ts`); change both.
- **`scripts/build-cache-pack.sh` runs from `node/`, so its default output is `node/build/<region>/cache-pack.zip`**, not `build/` at the repo root. The Sandbox looks there first. A Release asset must be named `cache-pack.zip`.
- **A coast Region's Flood-Prone Area is traced from the pack's zoom-12 terrain**, and "sea" is 0 m or lower, so any canal or marsh the terrain puts above 0 is traced as land; read a new threshold against the Region's shelters, which the build refuses inside it. Fort Myers builds from the Florida extract (about 1 GB, kept in `node/build/`) and its Overpass answer is large.
- **`pack_ian_event.py` writes the committed `regions/fort-myers/events/ian-2022.json`**; a test fails when the file is not what the sources build, so rerun the script after touching `region.json` (the gauge datum offset) or `sources/`.
- **Every httpx builder fetches through `http_retry.get_with_retries`** (the one streamed OpenStreetMap extract download aside, which fails the build with the error type). It prints only the error type and status, never `str(error)`: an httpx message holds the URL, which can carry a key.
- **`stn.wim.usgs.gov/STNServices` is gone: it redirects to a web page.** The STN data is at `api.waterdata.usgs.gov/stnservices/` (GET needs no key), and the sensors' water level is a NetCDF file; the recipe is in `regions/fort-myers/sources/README.md`. Keep every 30 s reading: the data swings at about the 6-minute filter period, so thinning to the gauge's 6-minute cadence misses the peaks.
