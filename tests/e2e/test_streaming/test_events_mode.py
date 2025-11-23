"""E2E tests for stream_mode="events" functionality (Issue #99)

Tests that stream_mode="events" works correctly and yields raw events including
on_chain_stream events, even when context is not provided.
"""

import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_events_mode_without_context():
    """
    Test that stream_mode="events" works correctly without context.

    This test verifies that:
    1. Raw 'events' events are yielded when stream_mode="events" is requested
    2. on_chain_stream events are included in the raw events
    3. No errors occur when context is None (workaround for LangGraph astream_events issue)
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["events-mode-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Stream with events mode without context
    events_count = 0
    events_events = 0
    on_chain_stream_count = 0
    error_events = []

    async for chunk in client.runs.stream(
        thread_id,
        assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "What is 2+2?"}]},
        stream_mode="events",
        # No context passed - this tests the None context workaround
    ):
        events_count += 1
        event_type = chunk.event if hasattr(chunk, "event") else None

        if event_type == "events":
            events_events += 1
            # Check if it's an on_chain_stream event
            data = chunk.data if hasattr(chunk, "data") else {}
            if isinstance(data, dict) and data.get("event") == "on_chain_stream":
                on_chain_stream_count += 1

        elif event_type == "error":
            data = chunk.data if hasattr(chunk, "data") else {}
            error_events.append(
                {
                    "error": data.get("error", "unknown"),
                    "message": data.get("message", "no message"),
                }
            )

        # Stop after reasonable number to avoid infinite loop
        if events_count > 100:
            break

    elog(
        "Streaming summary",
        {
            "total_events": events_count,
            "raw_events_events": events_events,
            "on_chain_stream_events": on_chain_stream_count,
            "error_events": error_events,
        },
    )

    # Assertions
    assert events_count > 1, "Should receive more than just metadata event"
    assert events_events > 0, (
        "Should receive raw 'events' events when stream_mode='events'"
    )
    assert on_chain_stream_count > 0, (
        f"Should receive on_chain_stream events. Got {on_chain_stream_count} on_chain_stream "
        f"events out of {events_events} total raw events"
    )
    assert len(error_events) == 0, (
        f"Should not receive any error events. Got errors: {error_events}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_events_mode_with_context():
    """
    Test that stream_mode="events" works correctly with context provided.

    This test verifies that events mode works when context is explicitly provided.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["events-mode-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 2. Stream with events mode with context
    events_count = 0
    events_events = 0
    on_chain_stream_count = 0
    error_events = []

    async for chunk in client.runs.stream(
        thread_id,
        assistant["assistant_id"],
        input={
            "messages": [{"role": "user", "content": "What is the weather in NYC?"}]
        },
        stream_mode="events",
        context={
            "model": "openai/gpt-4o-mini",
            "system_prompt": "You are a helpful assistant.",
            "max_search_results": 10,
        },
    ):
        events_count += 1
        event_type = chunk.event if hasattr(chunk, "event") else None

        if event_type == "events":
            events_events += 1
            # Check if it's an on_chain_stream event
            data = chunk.data if hasattr(chunk, "data") else {}
            if isinstance(data, dict) and data.get("event") == "on_chain_stream":
                on_chain_stream_count += 1

        elif event_type == "error":
            data = chunk.data if hasattr(chunk, "data") else {}
            error_events.append(
                {
                    "error": data.get("error", "unknown"),
                    "message": data.get("message", "no message"),
                }
            )

        # Stop after reasonable number to avoid infinite loop
        if events_count > 100:
            break

    elog(
        "Streaming summary",
        {
            "total_events": events_count,
            "raw_events_events": events_events,
            "on_chain_stream_events": on_chain_stream_count,
            "error_events": error_events,
        },
    )

    # Assertions
    assert events_count > 1, "Should receive more than just metadata event"
    assert events_events > 0, (
        "Should receive raw 'events' events when stream_mode='events'"
    )
    assert on_chain_stream_count > 0, (
        f"Should receive on_chain_stream events. Got {on_chain_stream_count} on_chain_stream "
        f"events out of {events_events} total raw events"
    )
    assert len(error_events) == 0, (
        f"Should not receive any error events. Got errors: {error_events}"
    )
