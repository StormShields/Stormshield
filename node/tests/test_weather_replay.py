import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fixture_pack import WEATHER_PATH, WEATHER_REPLAY, build_nepal_pack
from http_retry import ATTEMPTS, RequestFailed
from pack_weather import fetch_weather_replay, weather_replay_from_archive
from test_cache_pack import PackSource

from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.settings import Settings
from storm_shield.weather_grid import CREDIT, VARIABLES, grid_points

# Two rows by two columns, 0.5 degrees apart.
BBOX = (27.86, 85.08, 28.36, 85.58)
HOURS = ["2026-08-26T00:00", "2026-08-26T01:00", "2026-08-26T02:00"]


def _archive_answer(points: int = 4) -> list[dict[str, Any]]:
    """What Open-Meteo answers for several coordinates: one entry per point, values keyed by variable."""
    return [
        {
            "latitude": 27.873,
            "hourly": {
                "time": HOURS,
                **{
                    name: [point * 100 + hour + index for hour in range(len(HOURS))]
                    for index, name in enumerate(VARIABLES)
                },
            },
        }
        for point in range(points)
    ]


def _node(tmp_path: Path, source: httpx.Client) -> TestClient:
    settings = Settings(
        name="node", cache_pack_url="http://source/pack.zip", cache_pack_dir=tmp_path / "node"
    )
    return TestClient(create_app(settings, InMemoryNetwork().join("node"), pack_source=source))


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the Cache Pack"
        time.sleep(0.02)


def test_grid_runs_south_to_north_then_west_to_east_and_covers_the_box() -> None:
    rows, cols, points = grid_points((26.3, 80.0, 30.5, 88.3))
    assert (rows, cols) == (10, 18)
    assert len(points) == 180
    assert points[0] == (26.3, 80.0)
    assert points[1] == (26.3, 80.5)
    assert points[cols] == (26.8, 80.0)
    assert points[-1] == (30.8, 88.5)


def test_the_variables_are_temperature_cloud_and_rain_with_no_wind() -> None:
    assert VARIABLES == ("temperature_2m", "cloud_cover", "precipitation")


def test_the_file_holds_one_flat_array_per_variable_and_hour() -> None:
    weather = weather_replay_from_archive(_archive_answer(), BBOX)

    assert weather["grid"] == {
        "south": 27.86,
        "west": 85.08,
        "rows": 2,
        "cols": 2,
        "step_deg": 0.5,
    }
    assert weather["times"] == [f"{hour}Z" for hour in HOURS]
    assert set(weather["variables"]) == set(VARIABLES)
    # Hour 1 of temperature: points 0 to 3 in grid order, as the stub numbered them.
    assert weather["variables"]["temperature_2m"][1] == [1, 101, 201, 301]
    assert weather["credit"] == CREDIT
    assert weather["source"]
    assert weather["units"]["precipitation"] == "mm/h"


def test_the_grid_keeps_the_coordinates_we_asked_for_not_the_models() -> None:
    weather = weather_replay_from_archive(_archive_answer(), BBOX)
    assert "27.873" not in str(weather)


def test_an_answer_with_gaps_or_missing_points_is_refused() -> None:
    answer = _archive_answer()
    answer[2]["hourly"]["cloud_cover"][1] = None
    with pytest.raises(ValueError, match="cloud_cover"):
        weather_replay_from_archive(answer, BBOX)

    with pytest.raises(ValueError, match="4 points"):
        weather_replay_from_archive(_archive_answer(points=3), BBOX)


def test_one_request_asks_for_every_point() -> None:
    requests: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_archive_answer())

    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        weather = fetch_weather_replay(client, BBOX, "2026-08-26", "2026-08-26")

    assert len(requests) == 1
    query = requests[0].url.params
    assert query["latitude"] == "27.86,27.86,28.36,28.36"
    assert query["longitude"] == "85.08,85.58,85.08,85.58"
    assert query["timezone"] == "UTC"
    assert query["hourly"] == "temperature_2m,cloud_cover,precipitation"
    assert "wind_speed_unit" not in query
    assert len(weather["times"]) == 3


def test_a_node_serves_the_weather_from_its_pack(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(with_weather=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: node.get("/api/weather/replay").status_code == 200)
        assert node.get("/api/weather/replay").json() == WEATHER_REPLAY


def test_a_pack_without_weather_answers_404_with_a_message(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack())
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: node.get("/api/cache-pack").json()["available"])
        answer = node.get("/api/weather/replay")
    assert answer.status_code == 404
    assert "recorded weather" in answer.json()["detail"]


def test_a_node_with_no_pack_at_all_answers_404(tmp_path: Path) -> None:
    settings = Settings(cache_pack_dir=tmp_path / "empty")
    node = TestClient(create_app(settings, InMemoryNetwork().join(settings.name)))
    assert node.get("/api/weather/replay").status_code == 404


def test_a_pack_whose_weather_checksum_is_wrong_is_discarded(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(with_weather=True, corrupt_weather=True))
    with _node(tmp_path, source.client) as node:
        _wait_until(lambda: source.requests >= 1)
        time.sleep(0.2)
        assert not node.get("/api/cache-pack").json()["available"]
        assert node.get("/api/weather/replay").status_code == 404


def test_weather_corrupted_on_disk_discards_the_pack_at_startup(tmp_path: Path) -> None:
    source = PackSource(build_nepal_pack(with_weather=True))
    with _node(tmp_path, source.client) as first:
        _wait_until(lambda: first.get("/api/weather/replay").status_code == 200)
    (tmp_path / "node" / "files" / WEATHER_PATH).write_bytes(b"bit rot")

    source.running = False
    with _node(tmp_path, source.client) as restarted:
        assert restarted.get("/api/weather/replay").status_code == 404
        assert not restarted.get("/api/cache-pack").json()["available"]


def _flaky_archive(failures: list[httpx.Response | Exception]) -> tuple[httpx.Client, list[int]]:
    """A client whose first answers are the given failures, then a good archive answer."""
    calls: list[int] = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) <= len(failures):
            failure = failures[len(calls) - 1]
            if isinstance(failure, Exception):
                raise failure
            return failure
        return httpx.Response(200, json=_archive_answer())

    return httpx.Client(transport=httpx.MockTransport(answer)), calls


def test_a_failed_archive_request_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("http_retry.RETRY_PAUSE_SECONDS", 0)
    client, calls = _flaky_archive([httpx.Response(503), httpx.ConnectError("reset")])

    weather = fetch_weather_replay(client, BBOX, "2026-08-26", "2026-08-26")

    assert len(calls) == 3
    assert len(weather["times"]) == 3


def test_the_archive_request_gives_up_after_its_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("http_retry.RETRY_PAUSE_SECONDS", 0)
    client, calls = _flaky_archive([httpx.Response(503)] * 99)

    with pytest.raises(RequestFailed):
        fetch_weather_replay(client, BBOX, "2026-08-26", "2026-08-26")

    assert len(calls) == ATTEMPTS


def test_a_failed_request_reports_the_error_but_never_the_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("http_retry.RETRY_PAUSE_SECONDS", 0)
    client, _ = _flaky_archive([httpx.Response(503)] * 99)

    with pytest.raises(RequestFailed) as failure:
        fetch_weather_replay(client, BBOX, "2026-08-26", "2026-08-26")

    shown = capsys.readouterr().out + str(failure.value)
    assert "HTTP 503" in shown
    assert "archive-api.open-meteo.com" not in shown
