from typing import Any

import pytest

from tests.e2e._utils import elog, get_e2e_client


def _get_langgraph_node(chunk: Any) -> str:
    # Handle different event structures
    if isinstance(chunk, tuple) and len(chunk) >= 2:
        event_type, payload = chunk[0], chunk[1]

        # Handle namespaced event types (e.g., "messages|subagent")
        if isinstance(event_type, str) and "|" in event_type:
            event_type = event_type.split("|")[0]  # Extract base event type

        # For messages events, look in the message metadata
        if event_type == "messages" and isinstance(payload, list):
            for message in payload:
                if isinstance(message, dict) and "langgraph_node" in message:
                    return message["langgraph_node"]

        # For other events, check if payload has langgraph_node directly
        elif isinstance(payload, dict) and "langgraph_node" in payload:
            return payload["langgraph_node"]

    # Handle non-tuple chunks (direct objects)
    elif isinstance(chunk, dict) and "langgraph_node" in chunk:
        return chunk["langgraph_node"]

    # Handle SSE chunk objects with event attribute
    if hasattr(chunk, "event"):
        event_type = chunk.event
        if isinstance(event_type, str) and "|" in event_type:
            event_type = event_type.split("|")[0]
        if hasattr(chunk, "data"):
            data = chunk.data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "langgraph_node" in item:
                        return item["langgraph_node"]
            elif isinstance(data, dict) and "langgraph_node" in data:
                return data["langgraph_node"]

    return None


def _count_langgraph_nodes(langgraph_node_counts: dict, chunk: Any):
    langgraph_node = _get_langgraph_node(chunk)
    if langgraph_node:
        langgraph_node_counts[langgraph_node] = (
            langgraph_node_counts.get(langgraph_node, 0) + 1
        )

    event_type = getattr(chunk, "event", None)

    elog(
        "Subgraph streaming event",
        {
            "event": event_type,
            "langgraph_node_counts": langgraph_node_counts,
        },
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_langsmith_nostream_event_filtering_e2e():
    """
    Test that events containing 'langsmith:nostream' tag are properly filtered out
    during run execution. This validates the _should_skip_event function.

    Expected behavior:
    - Events with 'langsmith:nostream' tag should be skipped
    - Streaming should complete normally even with filtered events
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="subgraph_agent",
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Start a streaming run that would potentially generate events with langsmith:nostream tag
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello!",
                }
            ]
        },
        stream_mode=["messages", "values"],
    )

    # Track events to ensure subgraph events are included
    event_count = 0
    langgraph_node_counts = {}  # Track events by langgraph_node

    async for chunk in stream:
        _count_langgraph_nodes(langgraph_node_counts, chunk)
        event_count += 1
        # Stop after a reasonable number of events to avoid infinite loops
        if event_count >= 20:
            break

    # There should be no messages events from no_stream node.
    assert langgraph_node_counts.get("no_stream", 0) == 0, (
        "Should not receive any events from no_stream node"
    )

    # Validate that streaming produced events from subgraph_agent node.
    # We're expecting "subgraph_agent" node, not "call_model" node since we're not streaming subgraphs.
    assert langgraph_node_counts.get("subgraph_agent", 0) > 0, (
        "Should receive at least one event from subgraph_agent node"
    )

    elog(
        "Event filtering test completed",
        {"total_events": event_count, "langgraph_node_counts": langgraph_node_counts},
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_subgraphs_streaming_parameter_e2e():
    """
    Test that the subgraphs=True parameter is correctly applied in graph.astream()
    calls, enabling streaming events from subsequent graphs.

    Note: subgraphs defaults to False, so must be explicitly set to True.

    Expected behavior:
    - Events from subgraphs should be included in the stream when stream_subgraphs=True
    - The overall streaming should work correctly with subgraph events
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="subgraph_agent",
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Create a run that could trigger subgraph execution
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "Please process this request with multiple steps",
                }
            ]
        },
        stream_mode=["messages", "values"],
        stream_subgraphs=True,
    )

    # Track events to ensure subgraph events are included
    event_count = 0
    langgraph_node_counts = {}  # Track events by langgraph_node

    async for chunk in stream:
        _count_langgraph_nodes(langgraph_node_counts, chunk)
        event_count += 1
        # Stop after a reasonable number of events to avoid infinite loops
        if event_count >= 20:
            break

    # Validate streaming produced events from call_model node.
    # We're expecting "call_model" node, not "subgraph_agent" node since we're streaming subgraphs.
    assert langgraph_node_counts.get("call_model", 0) > 0, (
        "Should receive events from streaming"
    )

    elog(
        "Subgraphs streaming test completed",
        {
            "total_events": event_count,
            "langgraph_node_counts": langgraph_node_counts,
        },
    )
