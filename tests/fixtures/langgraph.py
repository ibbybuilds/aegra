"""LangGraph fixtures for tests"""

from typing import Any
from unittest.mock import patch

from langgraph.types import Interrupt, PregelTask


class FakeSnapshot:
    """Mock LangGraph snapshot"""

    def __init__(
        self,
        values: dict[str, Any],
        cfg: dict[str, Any],
        created_at=None,
        next_nodes: list[str] | tuple[str, ...] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        parent_config: dict[str, Any] | None = None,
        tasks: list[Any] | tuple[Any, ...] | None = None,
        interrupts: list[Any] | tuple[Any, ...] | None = None,
    ):
        self.values = values
        self.metadata = metadata or {}
        self.config = cfg
        self.parent_config = parent_config or {}
        self.created_at = created_at
        # Store ``next`` as list to match prior behaviour for tests expecting lists.
        if next_nodes is None:
            self.next = []
        elif isinstance(next_nodes, tuple):
            self.next = list(next_nodes)
        else:
            self.next = list(next_nodes)
        self.tasks = tuple(tasks) if tasks else ()
        self.interrupts = tuple(interrupts) if interrupts else ()


def make_interrupt(
    value: str = "Provide value:", interrupt_id: str = "fake-interrupt-id"
) -> Interrupt:
    """Create a LangGraph interrupt instance for tests."""

    return Interrupt(value=value, id=interrupt_id)


def make_task(**overrides) -> PregelTask:
    """Create a LangGraph task instance for tests."""

    defaults: dict[str, Any] = {
        "id": "task-1",
        "name": "node_1",
        "path": ("node_1",),
        "error": None,
        "interrupts": (make_interrupt(),),
        "state": None,
        "result": None,
    }
    defaults.update(overrides)

    interrupts = tuple(defaults.get("interrupts", ()))
    path = tuple(defaults.get("path", ()))

    return PregelTask(
        defaults["id"],
        defaults["name"],
        path,
        defaults.get("error"),
        interrupts,
        defaults.get("state"),
        defaults.get("result"),
    )


def make_snapshot(
    values: dict[str, Any],
    cfg: dict[str, Any],
    created_at=None,
    next_nodes: list[str] | tuple[str, ...] | None = None,
    *,
    metadata: dict[str, Any] | None = None,
    parent_config: dict[str, Any] | None = None,
    tasks: list[Any] | tuple[Any, ...] | None = None,
    interrupts: list[Any] | tuple[Any, ...] | None = None,
) -> FakeSnapshot:
    """Create a fake snapshot for testing"""
    return FakeSnapshot(
        values,
        cfg,
        created_at,
        next_nodes,
        metadata=metadata,
        parent_config=parent_config,
        tasks=tasks,
        interrupts=interrupts,
    )


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
        "agent_server.services.langgraph_service.get_langgraph_service",
        autospec=True,
        return_value=fake,
    )
