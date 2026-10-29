import pytest
from fastapi.testclient import TestClient

from storm_shield.main import create_app
from storm_shield.mesh import InMemoryNetwork
from storm_shield.settings import Settings


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, InMemoryNetwork().join(settings.name)))


def _identity(client: TestClient) -> dict[str, str]:
    node = client.get("/api/state").json()
    return {key: node[key] for key in ("id", "name", "role")}


def test_sensor_node_reports_its_id_name_and_role() -> None:
    client = _client(Settings(name="porch", role="sensor"))
    assert _identity(client) == {"id": "porch", "name": "porch", "role": "sensor"}


def test_hub_reports_the_hub_role() -> None:
    client = _client(Settings(name="hub", role="hub"))
    assert _identity(client) == {"id": "hub", "name": "hub", "role": "hub"}


def test_readings_are_aged_and_labeled_simulated() -> None:
    client = _client(Settings())
    [own] = client.get("/api/state").json()["nodes"]
    assert set(own["measurements"]) == {"air_pressure", "rain_rate", "soil_moisture"}
    assert own["simulated"]
    assert 0 <= own["age_s"] < 5


@pytest.mark.usefixtures("nepal_region")
def test_a_node_on_the_river_reads_the_events_first_moment() -> None:
    # S2's gauge at Syabrubesi reads 1.5 m at 08:30, with 3 mm/h of rain and 1005 hPa.
    client = _client(Settings(river_km=14.6))
    [own] = client.get("/api/state").json()["nodes"]
    assert {kind: m["value"] for kind, m in own["measurements"].items()} == {
        "air_pressure": 1005,
        "rain_rate": 3,
        "soil_moisture": 80,
        "water_level": 1.5,
    }
