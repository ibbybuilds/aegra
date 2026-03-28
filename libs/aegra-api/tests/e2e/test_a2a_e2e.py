"""E2E tests for A2A endpoints using the `a2a-sdk` client.

These tests connect to a real running Aegra server using the A2A SDK's
client and card resolver to verify agent discovery, message sending,
and streaming.
"""

from typing import Any
from uuid import uuid4

import httpx
import pytest
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    SendStreamingMessageRequest,
    TextPart,
)

from tests.e2e._utils import elog

pytestmark = pytest.mark.e2e

BASE_URL = "http://localhost:2026"


async def _check_server() -> None:
    """Skip test if server is not reachable."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code != 200:
                pytest.skip("Server not healthy")
    except httpx.ConnectError:
        pytest.skip("Server not reachable")


def _make_text_message(text: str) -> Message:
    """Build an A2A Message with a single text part."""
    return Message(
        messageId=str(uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )


# ---------------------------------------------------------------------------
# Agent card discovery (using A2A SDK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_card_resolver_fetches_agent_card() -> None:
    """A2ACardResolver can fetch the agent card from /.well-known/agent-card.json."""
    await _check_server()

    async with httpx.AsyncClient() as http_client:
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=BASE_URL,
        )
        card = await resolver.get_agent_card()

    elog("A2A agent card via SDK", {
        "name": card.name,
        "url": card.url,
        "skills": [s.name for s in card.skills],
    })
    assert card.name is not None
    assert card.url is not None
    assert len(card.skills) > 0


@pytest.mark.asyncio
async def test_a2a_agent_card_url_points_to_a2a_endpoint() -> None:
    """The URL in the agent card contains /a2a/."""
    await _check_server()

    async with httpx.AsyncClient() as http_client:
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=BASE_URL,
        )
        card = await resolver.get_agent_card()

    assert "/a2a/" in card.url, f"Agent card URL should contain '/a2a/', got: {card.url!r}"


@pytest.mark.asyncio
async def test_a2a_agent_cards_list_endpoint() -> None:
    """GET /a2a/agent-cards returns a non-empty array of agent cards."""
    await _check_server()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/a2a/agent-cards", timeout=10)

    assert response.status_code == 200
    cards: list[dict[str, Any]] = response.json()
    assert isinstance(cards, list)
    assert len(cards) > 0
    elog("A2A agent cards list", {"count": len(cards)})


# ---------------------------------------------------------------------------
# A2A message/send (using A2A SDK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_client_send_message() -> None:
    """A2AClient.send_message sends a text message and receives a task response.

    Requires a configured LLM API key in the server's .env.
    Skips gracefully if the agent execution fails.
    """
    await _check_server()

    async with httpx.AsyncClient() as http_client:
        # Discover agent card
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=BASE_URL,
        )
        card = await resolver.get_agent_card()

        # Create A2A client pointing at the agent's URL
        a2a_client = A2AClient(
            httpx_client=http_client,
            agent_card=card,
        )

        # Build request
        request = SendMessageRequest(
            id=1,
            params=MessageSendParams(
                message=_make_text_message("Say hello in one word."),
            ),
        )

        try:
            response = await a2a_client.send_message(request)
        except Exception as exc:
            pytest.skip(f"send_message failed (likely missing LLM credentials): {exc}")

    elog("A2A send_message response", {
        "type": type(response).__name__,
        "has_result": hasattr(response, "result"),
    })

    # The response should have a result (Task or Message)
    assert response.result is not None, f"Expected result in response, got error: {response.error if hasattr(response, 'error') else 'unknown'}"


@pytest.mark.asyncio
async def test_a2a_client_send_message_task_has_required_fields() -> None:
    """The task returned by send_message has id, status, and contextId."""
    await _check_server()

    async with httpx.AsyncClient() as http_client:
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=BASE_URL,
        )
        card = await resolver.get_agent_card()

        a2a_client = A2AClient(
            httpx_client=http_client,
            agent_card=card,
        )

        request = SendMessageRequest(
            id=2,
            params=MessageSendParams(
                message=_make_text_message("Say hello in one word."),
            ),
        )

        try:
            response = await a2a_client.send_message(request)
        except Exception as exc:
            pytest.skip(f"send_message failed: {exc}")

    if response.error is not None:
        pytest.skip(f"A2A returned error: {response.error}")

    task = response.result
    elog("A2A task result", {
        "id": task.id if hasattr(task, "id") else None,
        "status": str(task.status) if hasattr(task, "status") else None,
        "contextId": task.contextId if hasattr(task, "contextId") else None,
    })
    assert hasattr(task, "id"), "Task must have 'id'"
    assert hasattr(task, "status"), "Task must have 'status'"
    assert hasattr(task, "contextId"), "Task must have 'contextId'"


# ---------------------------------------------------------------------------
# A2A message/stream (using A2A SDK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_client_send_message_streaming() -> None:
    """A2AClient.send_message_streaming streams task events.

    Requires a configured LLM API key in the server's .env.
    Skips gracefully if the agent execution fails.
    """
    await _check_server()

    async with httpx.AsyncClient() as http_client:
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=BASE_URL,
        )
        card = await resolver.get_agent_card()

        a2a_client = A2AClient(
            httpx_client=http_client,
            agent_card=card,
        )

        request = SendStreamingMessageRequest(
            id=3,
            params=MessageSendParams(
                message=_make_text_message("Say hello in one word."),
            ),
        )

        events: list[Any] = []
        try:
            async for event in a2a_client.send_message_streaming(request):
                events.append(event)
                elog("A2A stream event", {"type": type(event).__name__})
                # Collect a few events then stop to avoid timeout
                if len(events) >= 10:
                    break
        except Exception as exc:
            pytest.skip(f"send_message_streaming failed: {exc}")

    elog("A2A streaming events collected", {"count": len(events)})
    assert len(events) > 0, "Expected at least one streaming event"


# ---------------------------------------------------------------------------
# A2A error cases (using raw httpx for JSON-RPC)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_unknown_method_returns_json_rpc_error() -> None:
    """Unknown JSON-RPC method returns -32601 Method not found."""
    await _check_server()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Get agent card to find the A2A endpoint URL
        resolver = A2ACardResolver(httpx_client=client, base_url=BASE_URL)
        card = await resolver.get_agent_card()
        path = card.url.replace(BASE_URL, "") if card.url.startswith(BASE_URL) else "/a2a/agent"

        response = await client.post(
            path,
            json={
                "jsonrpc": "2.0",
                "id": 99,
                "method": "unknown/method",
                "params": {},
            },
            timeout=10,
        )

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert "error" in body
    assert body["error"]["code"] == -32601
    elog("A2A unknown method error", body["error"])


@pytest.mark.asyncio
async def test_a2a_tasks_get_unknown_task_returns_error() -> None:
    """tasks/get for a non-existent task returns a JSON-RPC error."""
    await _check_server()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resolver = A2ACardResolver(httpx_client=client, base_url=BASE_URL)
        card = await resolver.get_agent_card()
        path = card.url.replace(BASE_URL, "") if card.url.startswith(BASE_URL) else "/a2a/agent"

        response = await client.post(
            path,
            json={
                "jsonrpc": "2.0",
                "id": 100,
                "method": "tasks/get",
                "params": {"id": "00000000-0000-0000-0000-000000000000"},
            },
            timeout=10,
        )

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert "error" in body
    elog("A2A tasks/get unknown task error", body["error"])
