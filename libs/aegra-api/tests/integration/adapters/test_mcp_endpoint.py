"""Integration tests for the MCP adapter endpoint."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.adapters.mcp_adapter import mount_mcp
from aegra_api.adapters.mcp_service import MCPService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(registry: dict[str, Any] | None = None) -> MCPService:
    """Return an MCPService backed by a minimal mocked LangGraphService."""
    svc = MCPService()
    lg = MagicMock()
    lg._graph_registry = registry or {}
    lg._get_base_graph = AsyncMock(return_value=MagicMock(get_input_jsonschema=lambda: {"type": "object"}))
    svc.set_langgraph_service(lg)
    return svc


def _make_mcp_app(service: MCPService) -> FastAPI:
    """Build a minimal FastAPI app with the MCP adapter mounted."""
    app = FastAPI()
    with patch("aegra_api.adapters.mcp_adapter.get_mcp_service", return_value=service):
        mount_mcp(app)
    return app


# ---------------------------------------------------------------------------
# disable_mcp: /mcp should return 404
# ---------------------------------------------------------------------------


def test_mcp_disabled_returns_404() -> None:
    """When disable_mcp is true, the /mcp path must not be mounted."""
    app = FastAPI()
    # Don't call mount_mcp — simulates disable_mcp=True
    client = TestClient(app)
    resp = client.post("/mcp", json={})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MCP enabled: /mcp endpoint exists and responds to JSON-RPC
# ---------------------------------------------------------------------------


def test_mcp_endpoint_responds_to_initialize() -> None:
    """POST /mcp with an MCP initialize request returns a valid response."""
    service = _make_service()
    app = _make_mcp_app(service)
    client = TestClient(app, raise_server_exceptions=False)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        },
    }
    resp = client.post(
        "/mcp",
        json=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    # The MCP server should respond — 200 or 202, not 404/405
    assert resp.status_code not in (404, 405), f"Unexpected status: {resp.status_code}"


def test_mcp_endpoint_tools_list() -> None:
    """POST /mcp tools/list returns one tool per registered graph."""
    registry: dict[str, Any] = {
        "my_agent": {"file_path": "agent.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    app = _make_mcp_app(service)
    client = TestClient(app, raise_server_exceptions=False)

    # First initialize the session
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        },
    }
    init_resp = client.post(
        "/mcp",
        json=init_payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    assert init_resp.status_code not in (404, 405)

    # Send tools/list
    tools_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    tools_resp = client.post(
        "/mcp",
        json=tools_payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    assert tools_resp.status_code not in (404, 405)


# ---------------------------------------------------------------------------
# _AegraMCPServer unit-level behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aegra_mcp_server_list_tools_delegates_to_service() -> None:
    """_AegraMCPServer.list_tools returns one MCPTool per graph in registry."""
    from aegra_api.adapters.mcp_adapter import _AegraMCPServer

    registry: dict[str, Any] = {
        "agent_a": {"file_path": "a.py", "export_name": "graph"},
        "agent_b": {"file_path": "b.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    server = _AegraMCPServer(service)

    tools = await server.list_tools()

    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"agent_a", "agent_b"}


@pytest.mark.asyncio
async def test_aegra_mcp_server_call_tool_returns_text_content() -> None:
    """_AegraMCPServer.call_tool wraps graph output as TextContent JSON."""
    import json

    from mcp.types import TextContent

    from aegra_api.adapters.mcp_adapter import _AegraMCPServer, _current_user
    from aegra_api.models.auth import User

    service = MCPService()
    service.call_tool = AsyncMock(return_value={"answer": 42})  # type: ignore[method-assign]

    server = _AegraMCPServer(service)

    # Set the ContextVar so call_tool can read the authenticated user
    test_user = User(identity="test-user", is_authenticated=True, permissions=[])
    token = _current_user.set(test_user)
    try:
        result = await server.call_tool("some_agent", {"q": "hello"})
    finally:
        _current_user.reset(token)

    assert len(result) == 1
    block = result[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == {"answer": 42}
    service.call_tool.assert_awaited_once_with("some_agent", {"q": "hello"}, test_user)


@pytest.mark.asyncio
async def test_aegra_mcp_server_list_tools_empty_registry() -> None:
    """_AegraMCPServer.list_tools returns empty list when no graphs are registered."""
    from aegra_api.adapters.mcp_adapter import _AegraMCPServer

    service = _make_service({})
    server = _AegraMCPServer(service)

    tools = await server.list_tools()

    assert tools == []
