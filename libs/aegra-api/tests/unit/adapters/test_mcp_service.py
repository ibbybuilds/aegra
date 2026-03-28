"""Unit tests for the MCP service layer."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegra_api.adapters.mcp_service import MCPService
from aegra_api.models.auth import User

_TEST_USER = User(identity="test-user", is_authenticated=True, permissions=[])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(registry: dict[str, Any]) -> MCPService:
    """Create an MCPService with a minimal mocked LangGraphService."""
    langgraph_service = MagicMock()
    langgraph_service._graph_registry = registry
    service = MCPService()
    service.set_langgraph_service(langgraph_service)
    return service


def _make_mock_graph(schema: dict[str, Any]) -> MagicMock:
    """Create a mock compiled Pregel graph with a given input schema."""
    graph = MagicMock()
    graph.get_input_jsonschema.return_value = schema
    return graph


# ---------------------------------------------------------------------------
# MCPService.list_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_tool_per_graph() -> None:
    """list_tools returns exactly one tool for each registered graph."""
    registry: dict[str, Any] = {
        "graph_a": {"file_path": "a.py", "export_name": "graph"},
        "graph_b": {"file_path": "b.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    service._langgraph_service._get_base_graph = AsyncMock(
        return_value=_make_mock_graph({"type": "object"})
    )

    tools = await service.list_tools()

    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert names == {"graph_a", "graph_b"}


@pytest.mark.asyncio
async def test_tool_has_input_schema_from_graph() -> None:
    """list_tools embeds the graph's input JSON schema under inputSchema."""
    expected_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"messages": {"type": "array"}},
    }
    registry: dict[str, Any] = {"my_agent": {"file_path": "x.py", "export_name": "graph"}}
    service = _make_service(registry)
    service._langgraph_service._get_base_graph = AsyncMock(
        return_value=_make_mock_graph(expected_schema)
    )

    tools = await service.list_tools()

    assert len(tools) == 1
    assert tools[0]["inputSchema"] == expected_schema


@pytest.mark.asyncio
async def test_tool_description_uses_graph_id() -> None:
    """list_tools sets description to 'Run the {graph_id} agent'."""
    registry: dict[str, Any] = {"cool_graph": {"file_path": "y.py", "export_name": "graph"}}
    service = _make_service(registry)
    service._langgraph_service._get_base_graph = AsyncMock(
        return_value=_make_mock_graph({"type": "object"})
    )

    tools = await service.list_tools()

    assert tools[0]["description"] == "Run the cool_graph agent"


@pytest.mark.asyncio
async def test_list_tools_skips_graph_that_fails_to_load() -> None:
    """list_tools omits any graph whose _get_base_graph raises."""
    registry: dict[str, Any] = {
        "good": {"file_path": "g.py", "export_name": "graph"},
        "bad": {"file_path": "b.py", "export_name": "graph"},
    }
    service = _make_service(registry)

    async def _get_base_graph_side_effect(graph_id: str) -> MagicMock:
        if graph_id == "bad":
            raise ValueError("Cannot load graph")
        return _make_mock_graph({"type": "object"})

    service._langgraph_service._get_base_graph = AsyncMock(
        side_effect=_get_base_graph_side_effect
    )

    tools = await service.list_tools()

    assert len(tools) == 1
    assert tools[0]["name"] == "good"


# ---------------------------------------------------------------------------
# MCPService.call_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_raises_value_error() -> None:
    """call_tool raises ValueError for an unregistered tool name."""
    registry: dict[str, Any] = {"existing": {"file_path": "e.py", "export_name": "graph"}}
    service = _make_service(registry)

    with pytest.raises(ValueError, match="Unknown tool"):
        await service.call_tool("nonexistent", {}, _TEST_USER)


@pytest.mark.asyncio
async def test_call_tool_delegates_to_wait_for_run() -> None:
    """call_tool delegates execution to wait_for_run and returns its output."""
    expected_output: dict[str, Any] = {"result": "hello"}
    registry: dict[str, Any] = {"agent": {"file_path": "a.py", "export_name": "graph"}}
    service = _make_service(registry)

    with patch(
        "aegra_api.adapters.mcp_service.stateless_wait_for_run",
        new=AsyncMock(return_value=expected_output),
    ):
        result = await service.call_tool("agent", {"messages": []}, _TEST_USER)

    assert result == expected_output


@pytest.mark.asyncio
async def test_call_tool_passes_graph_registry_to_resolve() -> None:
    """call_tool forwards the full graph registry to resolve_assistant_id."""
    registry: dict[str, Any] = {"my_graph": {"file_path": "m.py", "export_name": "graph"}}
    service = _make_service(registry)

    captured_calls: list[tuple[str, Any]] = []

    def _capture_resolve(requested_id: str, available_graphs: Any) -> str:
        captured_calls.append((requested_id, available_graphs))
        return "resolved-assistant-id"

    with (
        patch(
            "aegra_api.adapters.mcp_service.resolve_assistant_id",
            side_effect=_capture_resolve,
        ),
        patch(
            "aegra_api.adapters.mcp_service.stateless_wait_for_run",
            new=AsyncMock(return_value={}),
        ),
    ):
        await service.call_tool("my_graph", {}, _TEST_USER)

    assert len(captured_calls) == 1
    called_id, called_registry = captured_calls[0]
    assert called_id == "my_graph"
    assert called_registry is registry


@pytest.mark.asyncio
async def test_call_tool_creates_run_request_with_correct_fields() -> None:
    """call_tool builds a RunCreate with the resolved assistant_id and input."""
    registry: dict[str, Any] = {"agent": {"file_path": "a.py", "export_name": "graph"}}
    service = _make_service(registry)

    captured_request: list[Any] = []

    async def _capture_wait_for_run(request: Any, user: Any) -> dict[str, Any]:
        captured_request.append((request, user))
        return {}

    with patch(
        "aegra_api.adapters.mcp_service.stateless_wait_for_run",
        side_effect=_capture_wait_for_run,
    ):
        await service.call_tool("agent", {"messages": [{"role": "user", "content": "hi"}]}, _TEST_USER)

    assert len(captured_request) == 1
    req, user = captured_request[0]
    assert req.input == {"messages": [{"role": "user", "content": "hi"}]}
    assert user.identity == "test-user"
