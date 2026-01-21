"""E2E tests for ava_v1 graph."""

import pytest

from tests.e2e._utils import get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ava_v1_graph_registered():
    """Test that ava_v1 graph is registered."""
    client = get_e2e_client()

    assistants = await client.assistants.search()
    graph_ids = [a["graph_id"] for a in assistants]
    assert "ava_v1" in graph_ids, "ava_v1 graph should be registered"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ava_v1_with_context():
    """Test ava_v1 with call_context."""
    client = get_e2e_client()

    # Create thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # Create run with context
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id="ava_v1",
        input={"messages": [{"role": "user", "content": "Hello"}]},
        context={
            "call_context": {
                "type": "general",
                "user_phone": "+1234567890",
            }
        },
    )
    run_id = run["run_id"]

    # Verify run was created
    assert run_id is not None
    assert isinstance(run_id, str)
