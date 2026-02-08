import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_background_run_and_join_e2e():
    """
    End-to-end test that:
      1) Creates a background run (non-streaming)
      2) Streams the run (messages + values) while it's running
      3) Simulates a network drop and stores a last_event_id
      4) Rejoins the stream from last_event_id and continues consumption
      5) Joins for final state and validates thread history growth

    This mirrors the standalone script semantics while using the e2e helpers.
    """
    client = get_e2e_client()

    # Ensure assistant exists
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["chat", "background"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    assert "assistant_id" in assistant

    # Create thread
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # Initial history count
    initial_history = await client.threads.get_history(thread_id)
    elog("Threads.get_history initial", initial_history)
    initial_count = len(initial_history)

    # Create background run (non-streaming) and request messages+values availability
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Tell me a 200 word story."}]},
        stream_mode=["messages", "values"],
    )
    elog("Runs.create (background)", run)
    assert "run_id" in run
    run_id = run["run_id"]

    # Start streaming and simulate network drop after some events
    first_session_counters = {"messages": 0, "values": 0, "metadata": 0, "end": 0}
    last_event_id = None
    content_before_drop = ""
    event_count = 0

    async for chunk in client.runs.join_stream(
        thread_id=thread_id,
        run_id=run_id,
        stream_mode=["messages-tuple", "values"],  # accept alias, normalized on server
    ):
        event_count += 1
        first_session_counters[chunk.event] = first_session_counters.get(chunk.event, 0) + 1

        # Print/accumulate message content as it streams
        if (
            chunk.event == "messages"
            and hasattr(chunk, "data")
            and chunk.data
            and isinstance(chunk.data, list)
            and len(chunk.data) >= 1
        ):
            message_chunk = chunk.data[0]
            content = getattr(message_chunk, "content", None)
            if content is None and isinstance(message_chunk, dict):
                content = message_chunk.get("content")
            if content:
                content_before_drop += content

        # Create a simple mock event id for demonstration and simulate drop
        current_event_id = f"mock_event_{event_count}"
        if event_count >= 20:
            last_event_id = current_event_id
            elog("Simulated network drop", {"last_event_id": last_event_id})
            break

        # Natural end before simulated drop
        if chunk.event == "end":
            last_event_id = current_event_id
            elog("Stream ended before drop", {"last_event_id": last_event_id})
            break

    elog("First session counters", first_session_counters)
    assert event_count > 0, "Expected some events before network drop simulation"

    # Simulate reconnection delay
    # (Keep short to not slow the test; the real script used a longer sleep)
    import asyncio as _asyncio

    await _asyncio.sleep(0.25)

    # Rejoin from last_event_id (may be None if ended early)
    second_session_counters = {"messages": 0, "values": 0, "metadata": 0, "end": 0}
    content_after_rejoin = ""
    rejoin_event_count = 0
    rejoin_message_count = 0

    async for chunk in client.runs.join_stream(
        thread_id=thread_id,
        run_id=run_id,
        stream_mode=["messages", "values"],
        last_event_id=last_event_id,
    ):
        rejoin_event_count += 1
        second_session_counters[chunk.event] = second_session_counters.get(chunk.event, 0) + 1

        if chunk.event == "messages":
            rejoin_message_count += 1
            if hasattr(chunk, "data") and chunk.data and isinstance(chunk.data, list) and len(chunk.data) >= 1:
                message_chunk = chunk.data[0]
                content = getattr(message_chunk, "content", None)
                if content is None and isinstance(message_chunk, dict):
                    content = message_chunk.get("content")
                if content:
                    content_after_rejoin += content

        if chunk.event == "end":
            elog("Stream completed after rejoin", {})
            break

    # Basic validations similar to the standalone script intent
    combined_content = content_before_drop + content_after_rejoin
    elog("Rejoin session counters", second_session_counters)
    elog(
        "Content lengths",
        {
            "before": len(content_before_drop),
            "after": len(content_after_rejoin),
            "combined": len(combined_content),
        },
    )

    # Join run and verify final state
    final_state = await client.runs.join(thread_id, run_id)
    elog("Runs.join final_state", final_state)
    assert isinstance(final_state, dict)

    # History should have increased (at least by 1)
    after_history = await client.threads.get_history(thread_id)
    elog("Threads.get_history after", after_history)
    assert len(after_history) >= initial_count + 1
