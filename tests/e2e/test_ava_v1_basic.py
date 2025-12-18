"""E2E tests for ava_v1 graph."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ava_v1_graph_registered(client: AsyncClient):
    """Test that ava_v1 graph is registered."""
    response = await client.get("/assistants")
    assert response.status_code == 200

    assistants = response.json()
    graph_ids = [a["graph_id"] for a in assistants]
    assert "ava_v1" in graph_ids, "ava_v1 graph should be registered"


@pytest.mark.asyncio
async def test_ava_v1_with_context(client: AsyncClient):
    """Test ava_v1 with call_context."""
    # Create thread
    thread_response = await client.post("/threads", json={})
    assert thread_response.status_code == 201
    thread_id = thread_response.json()["thread_id"]

    # Create run with context
    run_response = await client.post(
        f"/threads/{thread_id}/runs",
        json={
            "assistant_id": "ava_v1",
            "input": {"messages": [{"role": "user", "content": "Hello"}]},
            "context": {
                "call_context": {
                    "type": "general",
                    "user_phone": "+1234567890",
                }
            },
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    # Verify run was created
    assert run_id is not None
    assert isinstance(run_id, str)
