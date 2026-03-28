"""Integration tests for A2A and MCP adapter authentication.

Verifies that:
- MCP auth middleware rejects unauthenticated requests
- MCP auth middleware passes authenticated user to tool handlers
- A2A RPC endpoint rejects unauthenticated requests
- A2A discovery endpoints (agent cards) don't require auth
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from starlette.authentication import AuthCredentials, AuthenticationError

from aegra_api.adapters.a2a_adapter import mount_a2a
from aegra_api.adapters.a2a_service import A2AService
from aegra_api.adapters.mcp_adapter import _AuthMiddleware, _current_user, mount_mcp
from aegra_api.adapters.mcp_service import MCPService
from aegra_api.core.auth_middleware import LangGraphUser
from aegra_api.models.auth import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mcp_service(registry: dict[str, Any] | None = None) -> MCPService:
    """Return an MCPService backed by a minimal mocked LangGraphService."""
    svc = MCPService()
    lg = MagicMock()
    lg._graph_registry = registry or {}
    lg._get_base_graph = AsyncMock(
        return_value=MagicMock(get_input_jsonschema=lambda: {"type": "object"})
    )
    svc.set_langgraph_service(lg)
    return svc


def _make_a2a_service(registry: dict[str, Any] | None = None) -> A2AService:
    """Return an A2AService backed by a minimal mocked LangGraphService."""
    svc = A2AService()
    lg = MagicMock()
    lg._graph_registry = registry or {}
    svc.set_langgraph_service(lg)
    return svc


def _make_auth_backend_that_rejects() -> MagicMock:
    """Return a mock auth backend that raises AuthenticationError."""
    backend = MagicMock()
    backend.authenticate = AsyncMock(side_effect=AuthenticationError("Invalid token"))
    return backend


def _make_auth_backend_that_accepts(
    identity: str = "test-user",
) -> MagicMock:
    """Return a mock auth backend that returns a valid user."""
    user_data = {"identity": identity, "is_authenticated": True}
    user = LangGraphUser(user_data)
    backend = MagicMock()
    backend.authenticate = AsyncMock(
        return_value=(AuthCredentials([]), user)
    )
    return backend


# ---------------------------------------------------------------------------
# MCP auth middleware tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_rejects_unauthenticated_request() -> None:
    """MCP endpoint returns 401 when auth backend rejects the request."""
    service = _make_mcp_service()

    app = FastAPI()
    with patch("aegra_api.adapters.mcp_adapter.get_mcp_service", return_value=service):
        mount_mcp(app)

    # Patch at request time so the auth rejection applies to the actual request
    # (not just mount time)
    with patch(
        "aegra_api.adapters.mcp_adapter.get_auth_backend",
        return_value=_make_auth_backend_that_rejects(),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                headers={"Accept": "application/json, text/event-stream"},
            )

    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_mcp_passes_authenticated_user_to_context_var() -> None:
    """MCP auth middleware stores authenticated user in ContextVar."""
    captured_users: list[User | None] = []

    # Create a custom ASGI app that reads the ContextVar
    async def _capture_app(scope: Any, receive: Any, send: Any) -> None:
        captured_users.append(_current_user.get())
        from starlette.responses import JSONResponse

        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    middleware = _AuthMiddleware(_capture_app)

    with patch(
        "aegra_api.adapters.mcp_adapter.get_auth_backend",
        return_value=_make_auth_backend_that_accepts("alice"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=middleware),
            base_url="http://test",
        ) as client:
            resp = await client.get("/anything")

    assert resp.status_code == 200
    assert len(captured_users) == 1
    assert captured_users[0] is not None
    assert captured_users[0].identity == "alice"


@pytest.mark.asyncio
async def test_mcp_context_var_cleared_after_request() -> None:
    """MCP ContextVar is reset after the request completes."""
    # Before any request, ContextVar should be None
    assert _current_user.get() is None

    async def _noop_app(scope: Any, receive: Any, send: Any) -> None:
        from starlette.responses import JSONResponse

        response = JSONResponse({"ok": True})
        await response(scope, receive, send)

    middleware = _AuthMiddleware(_noop_app)

    with patch(
        "aegra_api.adapters.mcp_adapter.get_auth_backend",
        return_value=_make_auth_backend_that_accepts("bob"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=middleware),
            base_url="http://test",
        ) as client:
            await client.get("/anything")

    # After request completes, ContextVar should be reset to None
    assert _current_user.get() is None


# ---------------------------------------------------------------------------
# A2A auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_rpc_rejects_unauthenticated_request() -> None:
    """A2A JSON-RPC endpoint returns 401 when auth rejects the user."""
    from fastapi import HTTPException

    from aegra_api.core.auth_deps import get_current_user
    from aegra_api.core.orm import get_session

    service = _make_a2a_service({"agent": {}})

    app = FastAPI()
    with patch("aegra_api.adapters.a2a_adapter.get_a2a_service", return_value=service):
        mount_a2a(app)

    # Override get_current_user to raise 401 (simulates failed auth)
    def _reject_user() -> None:
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _reject_user
    app.dependency_overrides[get_session] = lambda: AsyncMock()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/a2a/agent",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"parts": [{"kind": "text", "text": "hi"}]}},
            },
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a2a_discovery_endpoints_dont_require_auth() -> None:
    """Agent card discovery endpoints work without authentication."""
    service = _make_a2a_service({"agent": {}})

    app = FastAPI()
    with patch("aegra_api.adapters.a2a_adapter.get_a2a_service", return_value=service):
        mount_a2a(app)

    # Do NOT override auth — discovery should still work
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        card_resp = await client.get("/.well-known/agent-card.json")
        cards_resp = await client.get("/a2a/agent-cards")

    assert card_resp.status_code == 200
    assert cards_resp.status_code == 200


@pytest.mark.asyncio
async def test_a2a_rpc_accepts_authenticated_user() -> None:
    """A2A JSON-RPC endpoint works with authenticated user."""
    from aegra_api.core.auth_deps import get_current_user
    from aegra_api.core.orm import get_session

    service = _make_a2a_service({"agent": {}})
    service.send_message = AsyncMock(return_value={  # type: ignore[method-assign]
        "id": "run-1",
        "contextId": "thread-1",
        "status": {"state": "completed"},
        "artifacts": None,
    })

    app = FastAPI()
    with patch("aegra_api.adapters.a2a_adapter.get_a2a_service", return_value=service):
        mount_a2a(app)

    test_user = User(identity="alice", is_authenticated=True, permissions=[])
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: AsyncMock()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/a2a/agent",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"parts": [{"kind": "text", "text": "hello"}]}},
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body

    # Verify the service received the authenticated user
    service.send_message.assert_awaited_once()
    call_kwargs = service.send_message.call_args.kwargs
    assert call_kwargs["user"].identity == "alice"
