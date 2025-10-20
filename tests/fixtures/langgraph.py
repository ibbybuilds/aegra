"""LangGraph fixtures for tests"""

from typing import Any
from unittest.mock import patch


class FakeSnapshot:
    """Mock LangGraph snapshot"""

    def __init__(
        self,
        values: dict[str, Any],
        cfg: dict[str, Any],
        created_at=None,
        next_nodes: list[str] | None = None,
    ):
        self.values = values
        self.metadata = {}
        self.config = cfg
        self.parent_config = {}
        self.created_at = created_at
        self.next = next_nodes or []


def make_snapshot(
    values: dict[str, Any],
    cfg: dict[str, Any],
    created_at=None,
    next_nodes: list[str] | None = None,
) -> FakeSnapshot:
    """Create a fake snapshot for testing"""
    return FakeSnapshot(values, cfg, created_at, next_nodes)


class FakeAgent:
    """Mock LangGraph agent"""

    def __init__(self, snapshots: list[FakeSnapshot]):
        self._snapshots = snapshots

    async def aget_state_history(self, config, **_kwargs):
        for s in self._snapshots:
            yield s


class FakeGraph:
    """Mock LangGraph graph"""

    def __init__(self, events: list[Any]):
        self._events = events

    async def astream(self, _input, config=None, stream_mode=None):
        for e in self._events:
            yield e


class MockLangGraphService:
    """Mock LangGraph service"""

    def __init__(self, agent: FakeAgent | None = None, graph: FakeGraph | None = None):
        self._agent = agent
        self._graph = graph

    async def get_graph(self, _graph_id: str):
        if self._agent is not None:
            return self._agent
        if self._graph is not None:
            return self._graph
        raise RuntimeError("No fake agent/graph configured")


def patch_langgraph_service(
    agent: FakeAgent | None = None, graph: FakeGraph | None = None
):
    """Patch get_langgraph_service to return a mock

    Usage:
        with patch_langgraph_service(agent=fake_agent):
            ... tests ...
    """
    fake = MockLangGraphService(agent=agent, graph=graph)
    return patch(
        "aegra.agent_server.services.langgraph_service.get_langgraph_service",
        autospec=True,
        return_value=fake,
    )
