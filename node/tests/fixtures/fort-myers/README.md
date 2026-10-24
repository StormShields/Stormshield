# Fort Myers fixture pack

`cache-pack.zip` is a small Cache Pack for tests: the real `regions/fort-myers/region.json`, its Shelters as the build writes them, and an empty Flood-Prone Area. It has no basemap, terrain, Routes or Events, so nothing a test reads from it ever needs the network.

It is made by `node/tests/fort_myers_pack.py`, not by `scripts/build-cache-pack.sh` (which fetches NOAA, USGS and OpenStreetMap). The build is deterministic, so `test_fort_myers_pack.py` rebuilds it and fails when the checked-in zip no longer matches the Region file. After changing `regions/fort-myers/region.json`, rebuild it from `node/`:

```sh
uv run python tests/fort_myers_pack.py
```
