from collections.abc import Iterator
from pathlib import Path

import pytest
from meshed_nodes import MeshedNodes


@pytest.fixture
def meshed_nodes(tmp_path: Path) -> Iterator[MeshedNodes]:
    nodes = MeshedNodes(tmp_path / "nodes")
    yield nodes
    nodes.close()


@pytest.fixture
def nepal_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nodes started in this test run on Nepal, for tests about the river, River km or its Replay."""
    monkeypatch.setenv("NODE_REGION", "nepal")
