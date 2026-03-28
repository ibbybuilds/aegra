"""Integration tests for the A2A adapter endpoints."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from aegra_api.adapters.a2a_adapter import mount_a2a
from aegra_api.adapters.a2a_service import A2AService
from aegra_api.core.auth_deps import get_current_user
from aegra_api.core.orm import get_session
from aegra_api.models.auth import User

_TEST_USER = User(identity="test-user", is_authenticated=True, permissions=[])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(registry: dict[str, Any] | None = None) -> A2AService:
    """Return an A2AService backed by a minimal mocked LangGraphService.

    Args:
        registry: Optional graph registry dict to use.

    Returns:
        Configured A2AService instance.
    """
    svc = A2AService()
    lg = MagicMock()
    lg._graph_registry = registry or {}
    svc.set_langgraph_service(lg)
    return svc


def _make_a2a_app(service: A2AService) -> FastAPI:
    """Build a minimal FastAPI app with the A2A adapter mounted.

    Args:
        service: The A2AService instance to inject.

    Returns:
        FastAPI application with A2A routes registered.
    """
    app = FastAPI()
    with patch("aegra_api.adapters.a2a_adapter.get_a2a_service", return_value=service):
        mount_a2a(app)
    # Override auth and session dependencies so tests don't require real auth/DB
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    return app


# ---------------------------------------------------------------------------
# test_a2a_disabled_returns_404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_disabled_returns_404() -> None:
    """When disable_a2a is true, /a2a/X must not be mounted (returns 404)."""
    # Simulate disable_a2a by NOT calling mount_a2a
    app = FastAPI()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/some-agent", json={})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_well_known_returns_agent_card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_well_known_returns_agent_card() -> None:
    """GET /.well-known/agent-card.json returns 200 with an agent card when agents exist."""
    registry: dict[str, Any] = {
        "my_agent": {"file_path": "agent.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")

    assert resp.status_code == 200
    card = resp.json()
    assert "name" in card
    assert "url" in card
    assert "my_agent" in card["url"]


@pytest.mark.asyncio
async def test_well_known_no_agents_returns_404() -> None:
    """GET /.well-known/agent-card.json returns 404 when no agents are registered."""
    service = _make_service({})
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_well_known_with_assistant_id_query_param() -> None:
    """GET /.well-known/agent-card.json?assistant_id=X returns card for that agent."""
    registry: dict[str, Any] = {
        "agent_a": {"file_path": "a.py", "export_name": "graph"},
        "agent_b": {"file_path": "b.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json", params={"assistant_id": "agent_b"})

    assert resp.status_code == 200
    card = resp.json()
    assert "agent_b" in card["url"]


@pytest.mark.asyncio
async def test_well_known_unknown_assistant_id_returns_404() -> None:
    """GET /.well-known/agent-card.json?assistant_id=unknown returns 404."""
    registry: dict[str, Any] = {"agent_a": {}}
    service = _make_service(registry)
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json", params={"assistant_id": "no_such_agent"})

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_agent_cards_list_returns_array
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_cards_list_returns_array() -> None:
    """GET /a2a/agent-cards returns a JSON array of agent cards."""
    registry: dict[str, Any] = {
        "agent_a": {"file_path": "a.py", "export_name": "graph"},
        "agent_b": {"file_path": "b.py", "export_name": "graph"},
    }
    service = _make_service(registry)
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/a2a/agent-cards")

    assert resp.status_code == 200
    cards = resp.json()
    assert isinstance(cards, list)
    assert len(cards) == 2
    urls = {c["url"] for c in cards}
    assert any("agent_a" in u for u in urls)
    assert any("agent_b" in u for u in urls)


@pytest.mark.asyncio
async def test_agent_cards_list_empty_when_no_agents() -> None:
    """GET /a2a/agent-cards returns an empty array when no agents are registered."""
    service = _make_service({})
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/a2a/agent-cards")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# test_unknown_method_returns_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_method_returns_error() -> None:
    """POST /a2a/X with an unknown JSON-RPC method returns -32601 error."""
    service = _make_service({"my_agent": {}})
    app = _make_a2a_app(service)

    payload = {"jsonrpc": "2.0", "id": 1, "method": "nonexistent/method", "params": {}}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/my_agent", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32601
    assert body["id"] == 1


# ---------------------------------------------------------------------------
# test_invalid_json_returns_parse_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_returns_parse_error() -> None:
    """POST /a2a/X with invalid JSON body returns -32700 parse error."""
    service = _make_service({"my_agent": {}})
    app = _make_a2a_app(service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/a2a/my_agent",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32700
    assert body["id"] is None


# ---------------------------------------------------------------------------
# test_message_send_delegates_to_service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_send_delegates_to_service() -> None:
    """POST /a2a/X with method=message/send calls service.send_message."""
    service = _make_service({"my_agent": {}})
    fake_task: dict[str, Any] = {
        "id": "run-1",
        "contextId": "ctx-1",
        "status": {"state": "completed"},
        "artifacts": None,
    }
    service.send_message = AsyncMock(return_value=fake_task)  # type: ignore[method-assign]
    app = _make_a2a_app(service)

    payload = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "message/send",
        "params": {
            "message": {
                "parts": [{"kind": "text", "text": "hello"}],
            }
        },
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/my_agent", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    assert body["id"] == 42
    service.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# test_tasks_get_delegates_to_service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_get_delegates_to_service() -> None:
    """POST /a2a/X with method=tasks/get calls service.get_task."""
    service = _make_service({"my_agent": {}})
    fake_task: dict[str, Any] = {
        "id": "run-99",
        "contextId": "ctx-99",
        "status": {"state": "completed"},
        "artifacts": None,
    }
    service.get_task = AsyncMock(return_value=fake_task)  # type: ignore[method-assign]
    app = _make_a2a_app(service)

    payload = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tasks/get",
        "params": {"id": "run-99"},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/my_agent", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["id"] == "run-99"
    assert body["id"] == 7
    service.get_task.assert_awaited_once_with("run-99")


# ---------------------------------------------------------------------------
# test_message_stream_returns_not_implemented
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_stream_returns_sse_response() -> None:
    """POST /a2a/X with method=message/stream returns text/event-stream."""
    service = _make_service({"my_agent": {}})

    async def _fake_stream(**kwargs: Any) -> AsyncIterator[str]:
        yield "data: {}\n\n"

    service.stream_message = MagicMock(return_value=_fake_stream())  # type: ignore[method-assign]
    app = _make_a2a_app(service)

    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "message/stream",
        "params": {"message": {"parts": [{"kind": "text", "text": "hi"}]}},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/my_agent", json=payload)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
