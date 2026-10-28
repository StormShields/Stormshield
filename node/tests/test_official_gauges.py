import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from fixture_pack import build_nepal_pack
from meshed_nodes import MeshedNodes

from storm_shield.official_gauge import OfficialGaugeLevel
from storm_shield.region import load_region, region_path

STATION = "8725520"
# Fort Myers has no Events yet, which a Node needs, so Nepal's Region stands in with Fort Myers's gauge.
REGION = load_region(region_path("nepal")).model_copy(
    update={"official_gauges": load_region(region_path("fort-myers")).official_gauges}
)


def _noaa(rows: list[dict[str, str]] | None, offline: bool = False) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        if offline:
            raise httpx.ConnectError("no internet", request=request)
        assert request.url.params["station"] == STATION
        return httpx.Response(200, json={"data": rows} if rows else {"error": {"message": "none"}})

    return httpx.Client(transport=httpx.MockTransport(answer))


def _gauges(client: TestClient) -> list[dict[str, object]]:
    return list(client.get("/api/state").json()["official_gauges"])


def _wait_for(check: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not check():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def _level(observed: int, level_m: float = 1.5, station: str = STATION) -> OfficialGaugeLevel:
    return OfficialGaugeLevel(agency="NOAA", station=station, level_m=level_m, observed=observed)


def _start(
    meshed_nodes: MeshedNodes, tmp_path: Path, gauge_source: httpx.Client | None = None
) -> None:
    meshed_nodes.start("porch", cache_pack=(tmp_path, build_nepal_pack()), loaded_region=REGION)
    if gauge_source:
        meshed_nodes.start_hub(
            gauge_source=gauge_source, gauge_poll_seconds=0.02, loaded_region=REGION
        )


def test_a_gauge_has_no_level_until_the_hub_announces_one(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    [gauge] = _gauges(meshed_nodes["porch"])
    assert gauge["station"] == STATION
    assert gauge["level_m"] is None


def test_an_announced_level_shows_on_every_node(meshed_nodes: MeshedNodes, tmp_path: Path) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.announce_official_gauge(_level(1_000, 1.5))
    [gauge] = _gauges(meshed_nodes["porch"])
    assert (gauge["level_m"], gauge["observed"]) == (1.5, 1_000)


def test_an_older_level_does_not_replace_a_newer_one(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.announce_official_gauge(_level(2_000, 2.0))
    meshed_nodes.announce_official_gauge(_level(1_000, 1.0))
    [gauge] = _gauges(meshed_nodes["porch"])
    assert gauge["level_m"] == 2.0


def test_a_level_from_anyone_but_the_hub_is_ignored(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.announce_official_gauge(_level(1_000), sender="rogue")
    [gauge] = _gauges(meshed_nodes["porch"])
    assert gauge["level_m"] is None


def test_a_station_the_region_does_not_list_is_ignored(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    meshed_nodes.announce_official_gauge(_level(1_000, station="0000000"))
    assert [gauge["level_m"] for gauge in _gauges(meshed_nodes["porch"])] == [None]


def test_a_level_always_fits_one_packet() -> None:
    assert len(_level(1_800_000_000, -12.345).model_dump_json().encode()) < 464


def test_the_hub_polls_noaa_and_every_node_gets_the_level_in_the_regions_datum(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    rows = [{"t": "2026-10-28 12:06", "v": "1.000"}]
    _start(meshed_nodes, tmp_path, _noaa(rows))
    _wait_for(lambda: _gauges(meshed_nodes["porch"])[0]["level_m"] is not None)
    [gauge] = _gauges(meshed_nodes["porch"])
    # NOAA's metres above MHHW plus the Region's 0.28 ft offset to NAVD88.
    assert gauge["level_m"] == round(1.0 + 0.28 * 0.3048, 3)
    assert gauge["observed"] == int(datetime(2026, 10, 28, 12, 6, tzinfo=UTC).timestamp())


def test_a_noaa_that_cannot_be_reached_or_has_no_data_announces_nothing(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path, _noaa(None, offline=True))
    time.sleep(0.2)
    assert _gauges(meshed_nodes["porch"])[0]["level_m"] is None


def test_an_official_gauge_never_changes_flood_risk(
    meshed_nodes: MeshedNodes, tmp_path: Path
) -> None:
    _start(meshed_nodes, tmp_path)
    before = meshed_nodes["porch"].get("/api/state").json()["flood_risk"]
    meshed_nodes.announce_official_gauge(_level(1_000, level_m=9.0))
    after = meshed_nodes["porch"].get("/api/state").json()["flood_risk"]
    assert _gauges(meshed_nodes["porch"])[0]["level_m"] == 9.0
    assert after == before
