from typing import Any

import pytest
from fastapi.testclient import TestClient
from meshed_nodes import MeshedNodes

pytestmark = pytest.mark.usefixtures("nepal_region")


def _flood_risk(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()["flood_risk"]  # type: ignore[no-any-return]


def _surge(meshed_nodes: MeshedNodes, node: str) -> None:
    meshed_nodes.hear_from(node, water_cm=20)
    meshed_nodes.advance(8)
    meshed_nodes.hear_from(node, water_cm=340)


def test_an_unverified_nodes_surge_changes_nothing_in_flood_risk(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")

    _surge(meshed_nodes, "stranger")

    risk = _flood_risk(meshed_nodes["porch"])
    assert risk["surged"] == []
    assert "water_surge" not in [reason["code"] for reason in risk["reasons"]]
    assert risk["level"] is None


def test_the_same_surge_from_a_registered_node_makes_flood_risk_high(
    meshed_nodes: MeshedNodes,
) -> None:
    meshed_nodes.start_hub()
    meshed_nodes.start("porch")
    meshed_nodes.announce_sign_up("s0", "s0")
    assert meshed_nodes["hub"].post("/api/registry/accept", json={"id": "s0"}).status_code == 200

    _surge(meshed_nodes, "s0")

    risk = _flood_risk(meshed_nodes["porch"])
    assert risk["surged"] == ["s0"]
    assert "water_surge" in [reason["code"] for reason in risk["reasons"]]
    assert risk["level"] == "high"
