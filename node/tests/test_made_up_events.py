import pytest
from meshed_nodes import MeshedNodes

from storm_shield.region import load_region, region_path
from storm_shield.replay import load_events


@pytest.mark.parametrize(
    ("region_name", "event_id", "hazard"),
    [
        ("fort-myers", "made-up-storm-surge", "storm_surge"),
        ("nepal", "made-up-flash-flood", "flash_flood"),
    ],
)
def test_each_region_ships_a_made_up_event_of_its_hazard(
    region_name: str, event_id: str, hazard: str
) -> None:
    events = load_events(load_region(region_path(region_name)))

    assert (events[event_id].real, events[event_id].hazard) == (False, hazard)


def test_the_picker_marks_a_made_up_event_as_not_real(meshed_nodes: MeshedNodes) -> None:
    meshed_nodes.start_hub(region="fort-myers")

    listed = meshed_nodes["hub"].get("/api/replay/events").json()["events"]

    assert [(event["id"], event["real"]) for event in listed] == [("made-up-storm-surge", False)]
