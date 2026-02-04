import pytest

from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chat_streaming_e2e():
    """
    End-to-end test for streaming a run via SDK.
    Consumes SSE until completion and validates end-of-stream behavior.
    """
    client = get_e2e_client()

    # Ensure assistant exists
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["chat", "stream"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    assert "assistant_id" in assistant

    # Create thread
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # Start streaming (messages mode for token streaming)
    # Use a longer, content-rich prompt to encourage tokenized streaming (matching standalone script semantics)
    prompt = "tell me a very short joke"

    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": prompt}]},
        stream_mode=["messages-tuple", "values"],
    )

    # Consume events and verify streaming works
    event_count = 0
    token_count = 0
    async for chunk in stream:
        event_count += 1
        elog(
            "Runs.stream event",
            {
                "event": getattr(chunk, "event", None),
                "data": getattr(chunk, "data", None),
            },
        )

        if getattr(chunk, "event", None) == "messages":
            data = getattr(chunk, "data", None)
            if isinstance(data, list) and len(data) >= 1:
                message_chunk = data[0]
                # message_chunk can be a pydantic object or plain dict
                content = getattr(message_chunk, "content", None)
                if content is None and isinstance(message_chunk, dict):
                    content = message_chunk.get("content")
                if content:
                    token_count += 1

    # Check for blocking if no tokens received
    if token_count == 0:
        runs = await client.runs.list(thread_id)
        if runs:
            last_run = runs[0]
            if last_run["status"] == "error":
                check_and_skip_if_geo_blocked(last_run)

    # Enforce streaming behavior: at least one event received
    assert event_count > 0, "Expected at least one event from streaming run"
    assert token_count > 0, (
        "Expected at least one token in messages stream since 'messages-tuple' was explicitly requested. "
        "Ensure OPENAI_API_KEY is set and the server uses a streaming-capable model."
    )
