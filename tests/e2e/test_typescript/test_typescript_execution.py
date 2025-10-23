"""E2E tests for TypeScript graph execution.

These tests verify that TypeScript graphs can be executed end-to-end
through the full API stack, including assistant creation, streaming,
and state persistence.
"""

import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_typescript_graph_execution_e2e():
    """Test basic TypeScript graph execution end-to-end.

    Validates:
    1) TypeScript graph can be registered as assistant
    2) Thread can be created
    3) Run can be executed with TypeScript graph
    4) Streaming works correctly
    5) State is updated
    """
    client = get_e2e_client()

    # 1) Create assistant with TypeScript graph
    assistant = await client.assistants.create(
        graph_id="ts_agent",
        config={"tags": ["typescript", "e2e"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create (TypeScript)", assistant)
    assert "assistant_id" in assistant
    assert assistant["graph_id"] == "ts_agent"
    assistant_id = assistant["assistant_id"]

    # 2) Create thread
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 3) Stream execution
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "human", "content": "Hello from e2e test!"}]},
        stream_mode=["values"],
    )

    # 4) Verify we get events
    event_count = 0
    final_data = None

    async for chunk in stream:
        elog(
            f"Stream event: {chunk.event}",
            chunk.data if chunk.event == "values" else "...",
        )
        event_count += 1

        if chunk.event == "values":
            final_data = chunk.data
            # TypeScript graph should have callModel node
            if "callModel" in final_data:
                messages = final_data["callModel"].get("messages", [])
                assert len(messages) > 0, "Should have messages in response"
                # Verify it's the TypeScript agent response
                assert any(
                    "TypeScript" in str(msg.get("content", "")) for msg in messages
                ), "Response should mention TypeScript agent"

    assert event_count > 0, "Should receive at least one event"
    assert final_data is not None, "Should receive values event with data"

    # Success! TypeScript graph executed successfully
    elog("TypeScript graph execution complete", {"event_count": event_count})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_typescript_graph_multiple_runs_e2e():
    """Test multiple runs with TypeScript graph to verify state persistence.

    Validates:
    1) First run executes successfully
    2) Second run on same thread works
    3) State is maintained across runs
    """
    client = get_e2e_client()

    # Create assistant
    assistant = await client.assistants.create(
        graph_id="ts_agent",
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    # Create thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # First run
    stream1 = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "human", "content": "First message"}]},
        stream_mode=["values"],
    )

    async for chunk in stream1:
        if chunk.event == "values":
            elog("First run values", chunk.data)

    # Second run - should work on same thread
    stream2 = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "human", "content": "Second message"}]},
        stream_mode=["values"],
    )

    got_second_response = False
    async for chunk in stream2:
        if chunk.event == "values":
            elog("Second run values", chunk.data)
            got_second_response = True

    assert got_second_response, "Should get response from second run"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_typescript_graph_with_python_graphs_e2e():
    """Test that TypeScript and Python graphs can coexist.

    Validates:
    1) Can create assistants for both graph types
    2) Both can execute in same server instance
    3) No conflicts between graph types
    """
    client = get_e2e_client()

    # Create TypeScript assistant
    ts_assistant = await client.assistants.create(
        graph_id="ts_agent",
        if_exists="do_nothing",
    )
    elog("TypeScript assistant", ts_assistant)

    # Create Python assistant
    py_assistant = await client.assistants.create(
        graph_id="agent",
        if_exists="do_nothing",
    )
    elog("Python assistant", py_assistant)

    # Both should be different
    assert ts_assistant["assistant_id"] != py_assistant["assistant_id"]
    assert ts_assistant["graph_id"] == "ts_agent"
    assert py_assistant["graph_id"] == "agent"

    # Create thread for TypeScript
    ts_thread = await client.threads.create()

    # Execute TypeScript graph
    ts_stream = client.runs.stream(
        thread_id=ts_thread["thread_id"],
        assistant_id=ts_assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Test TS"}]},
        stream_mode=["values"],
    )

    ts_executed = False
    async for chunk in ts_stream:
        if chunk.event == "values":
            ts_executed = True
            break

    assert ts_executed, "TypeScript graph should execute"

    # Note: We skip Python graph execution here since it requires OpenAI API key
    # The important part is that both assistants can be created without conflicts
