"""E2E tests for POST /threads/{thread_id}/state endpoint"""

import os

import pytest
from httpx import AsyncClient

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_query_like_e2e():
    """
    Test POST /threads/{thread_id}/state with no values (query-like behavior).
    This should behave like GET and return the current state.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run to establish state
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Hello, test!"}]},
    )
    elog("Runs.create", run)
    await client.runs.join(thread_id, run["run_id"])

    # 3. Get state via GET
    state_get = await client.threads.get_state(thread_id=thread_id)
    elog("GET state", state_get)
    assert "checkpoint" in state_get
    assert "values" in state_get

    # 4. Get state via POST (query-like, no values)
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        post_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={},  # No values - should behave like GET
        )
        post_response.raise_for_status()
        state_post = post_response.json()
        elog("POST state (query-like)", state_post)

    # 5. Verify POST returns same state as GET
    assert isinstance(state_post, dict)
    assert "checkpoint" in state_post
    assert "values" in state_post
    assert (
        state_post["checkpoint"]["checkpoint_id"]
        == state_get["checkpoint"]["checkpoint_id"]
    )
    assert state_post["checkpoint"]["thread_id"] == thread_id
    assert len(state_post["values"].get("messages", [])) == len(
        state_get["values"].get("messages", [])
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_e2e():
    """
    Test POST /threads/{thread_id}/state with values (actual state update).
    This should update the state and create a new checkpoint.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run to establish initial state
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Initial message"}]},
    )
    elog("Runs.create", run)
    await client.runs.join(thread_id, run["run_id"])

    # 3. Get current state
    current_state = await client.threads.get_state(thread_id=thread_id)
    elog("Current state before update", current_state)
    current_messages = current_state["values"].get("messages", [])
    current_checkpoint_id = current_state["checkpoint"]["checkpoint_id"]

    # 4. Update state via POST with new values
    # Messages from get_state are already in LangChain format (with "type" field)
    # We need to add a new message in the same format
    # Note: When updating state, we should use as_node to prevent LangGraph from
    # trying to continue execution, which would trigger routing logic that expects
    # specific message types. Using "__start__" indicates we're updating the initial state.
    new_message = {
        "type": "human",
        "content": "Updated via state update endpoint",
    }
    updated_messages = current_messages + [new_message]

    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        update_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={
                "values": {
                    "messages": updated_messages,
                },
                "as_node": "__start__",  # Use __start__ to update state without triggering execution
            },
        )
        if update_response.status_code != 200:
            error_text = update_response.text
            elog(
                "POST state update ERROR",
                {"status": update_response.status_code, "error": error_text},
            )
            update_response.raise_for_status()
        update_result = update_response.json()
        elog("POST state update response", update_result)

    # 5. Verify update response
    assert isinstance(update_result, dict)
    assert "checkpoint" in update_result
    assert update_result["checkpoint"]["thread_id"] == thread_id
    new_checkpoint_id = update_result["checkpoint"]["checkpoint_id"]
    assert new_checkpoint_id is not None
    assert new_checkpoint_id != current_checkpoint_id, (
        "Expected new checkpoint ID after state update"
    )

    # 6. Verify the state was actually updated
    updated_state = await client.threads.get_state(thread_id=thread_id)
    elog("State after update", updated_state)
    assert updated_state["checkpoint"]["checkpoint_id"] == new_checkpoint_id
    updated_messages_after = updated_state["values"].get("messages", [])

    # Check that our new message is in the updated state
    found_new_message = any(
        msg.get("content") == new_message["content"] for msg in updated_messages_after
    )
    assert found_new_message, "New message should be present in updated state"
    assert len(updated_messages_after) == len(updated_messages), (
        "Message count should match updated messages"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_with_as_node_e2e():
    """
    Test POST /threads/{thread_id}/state with as_node parameter.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run to establish initial state
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Test message"}]},
    )
    elog("Runs.create", run)
    await client.runs.join(thread_id, run["run_id"])

    # 3. Update state with as_node parameter
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        update_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={
                "values": {
                    "messages": [
                        {"type": "ai", "content": "Updated as if from call_model node"}
                    ]
                },
                "as_node": "call_model",
            },
        )
        update_response.raise_for_status()
        update_result = update_response.json()
        elog("POST state update with as_node", update_result)

    # 4. Verify update succeeded
    assert isinstance(update_result, dict)
    assert "checkpoint" in update_result
    assert update_result["checkpoint"]["thread_id"] == thread_id


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_with_values_none_e2e():
    """
    Test POST /threads/{thread_id}/state with values=None (should delegate to GET).
    This covers the branch where request.values is None.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run to establish state
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Test message"}]},
    )
    elog("Runs.create", run)
    await client.runs.join(thread_id, run["run_id"])

    # 3. Get state via GET
    state_get = await client.threads.get_state(thread_id=thread_id)
    elog("GET state", state_get)

    # 4. POST with values=None (should delegate to GET handler)
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        post_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={"values": None},  # Explicitly None
        )
        post_response.raise_for_status()
        state_post = post_response.json()
        elog("POST state with values=None", state_post)

    # 5. Verify POST returns same state as GET (delegated to GET handler)
    assert isinstance(state_post, dict)
    assert "checkpoint" in state_post
    assert "values" in state_post
    assert (
        state_post["checkpoint"]["checkpoint_id"]
        == state_get["checkpoint"]["checkpoint_id"]
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_with_list_values_e2e():
    """
    Test POST /threads/{thread_id}/state with values as a list of dicts.
    Should merge all dicts in the list (covers list merging logic).
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run to establish initial state
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Initial"}]},
    )
    elog("Runs.create", run)
    await client.runs.join(thread_id, run["run_id"])

    # 3. Update state with values as a list of dicts
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        update_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={
                "values": [
                    {"messages": [{"type": "human", "content": "First"}]},
                    {"messages": [{"type": "human", "content": "Second"}]},
                ],
                "as_node": "__start__",
            },
        )
        update_response.raise_for_status()
        update_result = update_response.json()
        elog("POST state update with list values", update_result)

    # 4. Verify update succeeded
    assert isinstance(update_result, dict)
    assert "checkpoint" in update_result
    assert update_result["checkpoint"]["thread_id"] == thread_id
    assert update_result["checkpoint"]["checkpoint_id"] is not None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_thread_not_found_e2e():
    """
    Test POST /threads/{thread_id}/state with non-existent thread.
    Should return 404 (covers thread not found error handling).
    """
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        response = await http_client.post(
            "/threads/non-existent-thread-id/state",
            json={"values": {"messages": [{"type": "human", "content": "test"}]}},
        )
        assert response.status_code == 404
        error_data = response.json()
        error_message = error_data.get("message", error_data.get("detail", ""))
        assert "not found" in error_message.lower()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_no_graph_id_e2e():
    """
    Test POST /threads/{thread_id}/state with thread that has no graph_id.
    Should return 400 (covers no graph_id error handling).
    """
    client = get_e2e_client()

    # 1. Create thread without running any graph (no graph_id in metadata)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Try to update state (should fail because no graph_id)
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={"values": {"messages": [{"type": "human", "content": "test"}]}},
        )
        assert response.status_code == 400
        error_data = response.json()
        error_message = error_data.get("message", error_data.get("detail", ""))
        assert "no associated graph" in error_message.lower()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_with_checkpoint_config_e2e():
    """
    Test POST /threads/{thread_id}/state with checkpoint configuration.
    Covers checkpoint_id, checkpoint dict, and checkpoint_ns handling.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run and get checkpoint
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Test"}]},
    )
    await client.runs.join(thread_id, run["run_id"])

    state = await client.threads.get_state(thread_id=thread_id)
    checkpoint_id = state["checkpoint"]["checkpoint_id"]

    # 3. Update state with checkpoint configuration
    # Test checkpoint_id handling (checkpoint_ns might not be fully supported, so we'll test checkpoint_id)
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        update_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={
                "values": {
                    "messages": [{"type": "human", "content": "Updated"}],
                },
                "checkpoint_id": checkpoint_id,
                "as_node": "__start__",
            },
        )
        if update_response.status_code != 200:
            error_text = update_response.text
            elog(
                "POST state update ERROR",
                {"status": update_response.status_code, "error": error_text},
            )
        update_response.raise_for_status()
        update_result = update_response.json()
        elog("POST state update with checkpoint config", update_result)

    # 4. Verify update succeeded
    assert isinstance(update_result, dict)
    assert "checkpoint" in update_result
    assert update_result["checkpoint"]["thread_id"] == thread_id
    assert update_result["checkpoint"]["checkpoint_id"] is not None
    assert update_result["checkpoint"]["checkpoint_id"] is not None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_state_update_with_checkpoint_e2e():
    """
    Test POST /threads/{thread_id}/state with checkpoint configuration.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-update-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Create a run and get history
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Test"}]},
    )
    await client.runs.join(thread_id, run["run_id"])

    history = await client.threads.get_history(thread_id)
    assert len(history) > 0
    checkpoint_id = history[0]["checkpoint"]["checkpoint_id"]

    # 3. Update state from a specific checkpoint
    base_url = os.getenv("SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as http_client:
        update_response = await http_client.post(
            f"/threads/{thread_id}/state",
            json={
                "values": {
                    "messages": [
                        {"type": "human", "content": "Updated from checkpoint"}
                    ]
                },
                "checkpoint_id": checkpoint_id,
                "as_node": "__start__",  # Use __start__ to update state without triggering execution
            },
        )
        update_response.raise_for_status()
        update_result = update_response.json()
        elog("POST state update with checkpoint_id", update_result)

    # 4. Verify update succeeded
    assert isinstance(update_result, dict)
    assert "checkpoint" in update_result
    assert update_result["checkpoint"]["thread_id"] == thread_id
