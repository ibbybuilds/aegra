import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_history_endpoint_e2e():
    """
    End-to-end test against a running server using the LangGraph SDK.
    This verifies assistant creation, run execution, join endpoint, and history retrieval.
    Requires the server to be running and accessible.
    """
    client = get_e2e_client()

    # Create an assistant (idempotent if server supports if_exists/do_nothing)
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["chat", "llm"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create response", assistant)
    assert "assistant_id" in assistant, f"Invalid assistant response: {assistant}"

    # Create a thread
    thread = await client.threads.create()
    elog("Threads.create response", thread)
    assert "thread_id" in thread, f"Invalid thread response: {thread}"
    thread_id = thread["thread_id"]

    # Initial history (likely empty)
    initial_history = await client.threads.get_history(thread_id)
    elog("Threads.get_history initial", initial_history)
    assert isinstance(initial_history, list)

    # Create a run and wait for completion using join (also validates join endpoint behavior)
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Hello! Tell me a short joke."}]},
    )
    elog("Runs.create response", run)
    assert "run_id" in run

    final_state = await client.runs.join(thread_id, run["run_id"])
    elog("Runs.join final_state", final_state)
    assert isinstance(final_state, dict)

    # Verify history has at least one snapshot after completing the run
    history_after = await client.threads.get_history(thread_id)
    elog("Threads.get_history after run", history_after)
    assert isinstance(history_after, list)
    assert len(history_after) >= 1, f"Expected at least one checkpoint after run; got {len(history_after)}"

    # Validate pagination with limit
    limited = await client.threads.get_history(thread_id, limit=1)
    elog("Threads.get_history limit=1", limited)
    assert isinstance(limited, list)
    assert len(limited) == 1
