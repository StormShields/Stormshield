import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.region import load_region, region_path
from storm_shield.settings import Settings
from storm_shield.weather_forecast import FILE_NAME
from storm_shield.weather_grid import VARIABLES, grid_points

# The box the default Region (Fort Myers) fills the grid over.
REGION_BBOX = load_region(region_path("fort-myers")).bbox
HOURS = ["2026-10-17T00:00", "2026-10-17T01:00"]
FORECAST_URL = "http://hub/api/weather/forecast"


def _open_meteo_answer(offset: int = 0) -> list[dict[str, Any]]:
    """What Open-Meteo answers for the Region's box: one entry per grid point, values keyed by variable."""
    _, _, points = grid_points(REGION_BBOX)
    return [
        {
            "hourly": {
                "time": HOURS,
                **{name: [offset + point, offset + point + 1] for name in VARIABLES},
            }
        }
        for point in range(len(points))
    ]


class OpenMeteo:
    """A stand-in for api.open-meteo.com that can be told to fail."""

    def __init__(self) -> None:
        self.answer: httpx.Response | Exception = httpx.Response(200, json=_open_meteo_answer())
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self._respond))

    def _respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture(autouse=True)
def _retry_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("storm_shield.main.RETRY_EVERY_SECONDS", 0.02)


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the forecast"
        time.sleep(0.02)


def _hub(directory: Path, source: OpenMeteo, refresh_seconds: float = 3600) -> TestClient:
    settings = Settings(
        name="hub", role="hub", data_dir=directory, weather_forecast_seconds=refresh_seconds
    )
    return TestClient(
        create_app(settings, InMemoryNetwork().join("hub"), weather_source=source.client)
    )


def _has_forecast(node: TestClient) -> bool:
    return bool(node.get("/api/weather/forecast").status_code == 200)


def test_the_hub_fetches_the_regions_grid_and_serves_it_with_its_fetch_time(
    tmp_path: Path,
) -> None:
    source = OpenMeteo()
    with _hub(tmp_path, source) as hub:
        _wait_until(lambda: _has_forecast(hub))
        forecast = hub.get("/api/weather/forecast").json()

    query = source.requests[0].url.params
    _, _, points = grid_points(REGION_BBOX)
    assert source.requests[0].url.host == "api.open-meteo.com"
    assert query["latitude"].split(",")[0] == str(points[0][0])
    assert len(query["latitude"].split(",")) == len(points)
    assert query["forecast_days"] == "7"
    assert forecast["times"] == [f"{hour}Z" for hour in HOURS]
    assert set(forecast["variables"]) == {"temperature_2m", "cloud_cover", "precipitation"}
    assert forecast["grid"]["rows"] * forecast["grid"]["cols"] == 4
    assert "wind_speed_unit" not in query
    assert forecast["fetched_at"]
    assert (tmp_path / FILE_NAME).is_file()


def test_a_node_with_no_forecast_answers_404(tmp_path: Path) -> None:
    settings = Settings(name="node", data_dir=tmp_path)
    node = TestClient(create_app(settings, InMemoryNetwork().join("node")))
    assert node.get("/api/weather/forecast").status_code == 404


def test_a_failed_or_malformed_fetch_keeps_the_old_copy(tmp_path: Path) -> None:
    source = OpenMeteo()
    with _hub(tmp_path, source, refresh_seconds=0.02) as hub:
        _wait_until(lambda: _has_forecast(hub))
        first = hub.get("/api/weather/forecast").json()

        for broken in (
            httpx.ConnectError("no internet"),
            httpx.Response(503),
            httpx.Response(200, json=_open_meteo_answer()[:3]),
        ):
            source.answer = broken
            seen = len(source.requests)
            _wait_until(lambda: len(source.requests) > seen + 1)  # noqa: B023
            assert hub.get("/api/weather/forecast").json() == first

        source.answer = httpx.Response(200, json=_open_meteo_answer(offset=50))
        _wait_until(lambda: hub.get("/api/weather/forecast").json() != first)


def test_a_corrupt_file_counts_as_absent_and_is_replaced_by_the_next_fetch(tmp_path: Path) -> None:
    (tmp_path / FILE_NAME).write_text("bit rot")
    source = OpenMeteo()
    source.answer = httpx.ConnectError("no internet")
    with _hub(tmp_path, source, refresh_seconds=0.02) as hub:
        _wait_until(lambda: len(source.requests) >= 1)
        assert hub.get("/api/weather/forecast").status_code == 404

        source.answer = httpx.Response(200, json=_open_meteo_answer())
        _wait_until(lambda: _has_forecast(hub))


@pytest.mark.parametrize("old", ["other_grid", "wind_variables"])
def test_a_file_for_another_grid_or_other_variables_counts_as_absent_and_is_fetched_again(
    tmp_path: Path, old: str
) -> None:
    source = OpenMeteo()
    with _hub(tmp_path, source) as hub:
        _wait_until(lambda: _has_forecast(hub))
    file = tmp_path / FILE_NAME
    weather = json.loads(file.read_text())
    if old == "other_grid":
        weather["grid"].update(south=26.3, west=80.0, rows=10, cols=18, step_deg=0.5)
    else:
        weather["variables"]["wind_speed_10m"] = weather["variables"]["temperature_2m"]
    file.write_text(json.dumps(weather))

    stale = OpenMeteo()
    stale.answer = httpx.ConnectError("no internet")
    with _hub(tmp_path, stale) as hub:
        _wait_until(lambda: len(stale.requests) >= 1)
        assert hub.get("/api/weather/forecast").status_code == 404

        stale.answer = httpx.Response(200, json=_open_meteo_answer())
        _wait_until(lambda: _has_forecast(hub))


def test_a_sensor_serves_what_it_downloaded_after_the_hub_stops(tmp_path: Path) -> None:
    source = OpenMeteo()
    hub_running = True

    def from_the_hub(request: httpx.Request) -> httpx.Response:
        if not hub_running:
            raise httpx.ConnectError("the Hub is gone", request=request)
        return httpx.Response(200, content=hub.get("/api/weather/forecast").content)

    sensor_settings = Settings(
        name="sensor",
        data_dir=tmp_path / "sensor",
        weather_forecast_url=FORECAST_URL,
        weather_forecast_seconds=0.02,
    )
    sensor = TestClient(
        create_app(
            sensor_settings,
            InMemoryNetwork().join("sensor"),
            weather_source=httpx.Client(transport=httpx.MockTransport(from_the_hub)),
        )
    )
    with _hub(tmp_path / "hub", source) as hub, sensor:
        _wait_until(lambda: _has_forecast(hub))
        _wait_until(lambda: _has_forecast(sensor))
        hub_running = False
        time.sleep(0.2)

        assert sensor.get("/api/weather/forecast").json() == hub.get("/api/weather/forecast").json()
