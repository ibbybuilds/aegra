"""E2E auth tests for A2A and MCP adapter endpoints.

These tests verify that:
- MCP endpoint rejects requests without valid auth when auth is enabled
- MCP endpoint accepts requests with valid auth headers
- A2A RPC endpoint rejects requests without valid auth when auth is enabled
- A2A RPC endpoint accepts requests with valid auth headers
- A2A discovery endpoints work without auth even when auth is enabled

Requires a server started with auth enabled.
Run with: pytest tests/e2e/test_adapter_auth_e2e.py -v -m manual_auth
"""

from typing import Any

import httpx
import pytest

from tests.e2e._utils import check_server_has_auth, elog

pytestmark = [pytest.mark.e2e, pytest.mark.manual_auth]

BASE_URL = "http://localhost:2026"


async def _check_server_with_auth() -> None:
    """Skip if server is not reachable or auth is not enabled."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code != 200:
                pytest.skip("Server not healthy")
    except httpx.ConnectError:
        pytest.skip("Server not reachable")

    has_auth = check_server_has_auth(BASE_URL)
    if not has_auth:
        pytest.skip("Server does not have auth enabled")


def _get_auth_headers(
    user_id: str = "alice", role: str = "user", team_id: str = "team123",
) -> dict[str, str]:
    """Generate mock JWT auth headers for testing."""
    token = f"mock-jwt-{user_id}-{role}-{team_id}"
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# MCP auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_rejects_unauthenticated_request() -> None:
    """MCP /mcp endpoint returns 401 without auth headers."""
    await _check_server_with_auth()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
            timeout=10,
        )

    elog("MCP unauthenticated response", {"status": resp.status_code})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_accepts_authenticated_request() -> None:
    """MCP /mcp endpoint accepts requests with valid auth headers."""
    await _check_server_with_auth()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={
                "Accept": "application/json, text/event-stream",
                **_get_auth_headers(),
            },
            timeout=10,
        )

    elog("MCP authenticated response", {"status": resp.status_code})
    assert resp.status_code != 401, f"Expected non-401, got {resp.status_code}"


# ---------------------------------------------------------------------------
# A2A auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_rpc_rejects_unauthenticated_request() -> None:
    """A2A /a2a/{id} endpoint returns 401 without auth headers."""
    await _check_server_with_auth()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Get agent card (discovery, no auth needed)
        card_resp = await client.get("/.well-known/agent-card.json")
        assert card_resp.status_code == 200
        card: dict[str, Any] = card_resp.json()
        url: str = card.get("url", "")
        path = url.replace(BASE_URL, "") if url.startswith(BASE_URL) else "/a2a/agent"

        # Try RPC without auth
        resp = await client.post(
            path,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "hi"}],
                    }
                },
            },
            timeout=10,
        )

    elog("A2A unauthenticated RPC response", {"status": resp.status_code})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a2a_rpc_accepts_authenticated_request() -> None:
    """A2A /a2a/{id} endpoint accepts requests with valid auth headers."""
    await _check_server_with_auth()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        card_resp = await client.get("/.well-known/agent-card.json")
        assert card_resp.status_code == 200
        card: dict[str, Any] = card_resp.json()
        url: str = card.get("url", "")
        path = url.replace(BASE_URL, "") if url.startswith(BASE_URL) else "/a2a/agent"

        resp = await client.post(
            path,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "hi"}],
                    }
                },
            },
            headers=_get_auth_headers(),
            timeout=60,
        )

    elog("A2A authenticated RPC response", {"status": resp.status_code})
    assert resp.status_code != 401, f"Expected non-401, got {resp.status_code}"


@pytest.mark.asyncio
async def test_a2a_discovery_works_without_auth() -> None:
    """A2A agent card endpoints work without auth even when auth is enabled."""
    await _check_server_with_auth()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        card_resp = await client.get("/.well-known/agent-card.json", timeout=10)
        cards_resp = await client.get("/a2a/agent-cards", timeout=10)

    elog("A2A discovery without auth", {
        "card_status": card_resp.status_code,
        "cards_status": cards_resp.status_code,
    })
    assert card_resp.status_code == 200, "Agent card should be accessible without auth"
    assert cards_resp.status_code == 200, "Agent cards list should be accessible without auth"
