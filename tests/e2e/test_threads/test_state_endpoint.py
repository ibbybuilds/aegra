import pytest
from langgraph_sdk.schema import Checkpoint

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_state_at_checkpoint_e2e():
    """
    End-to-end test for fetching thread state at a specific checkpoint.
    """
    client = get_e2e_client()

    # 1. Create an assistant
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["state-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create response", assistant)
    assert "assistant_id" in assistant

    # 2. Create a thread
    thread = await client.threads.create()
    elog("Threads.create response", thread)
    assert "thread_id" in thread
    thread_id = thread["thread_id"]

    # 3. Run the agent to generate history and checkpoints
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={
            "messages": [{"role": "human", "content": "What is the capital of France?"}]
        },
    )
    elog("Runs.create response", run)
    final_state = await client.runs.join(thread_id, run["run_id"])
    elog("Run joined, final state", final_state)

    # 4. Get history and a valid checkpoint ID from the completed run
    history = await client.threads.get_history(thread_id)
    elog("Threads.get_history response", history)
    assert isinstance(history, list)
    assert len(history) > 0, "History should not be empty after a run"

    latest_checkpoint_info = history[0]["checkpoint"]
    checkpoint_id = latest_checkpoint_info["checkpoint_id"]
    checkpoint_ns = latest_checkpoint_info.get("checkpoint_ns", "")
    elog(f"Using checkpoint_id for test: {checkpoint_id}", None)

    # 5. Test GET endpoint: /threads/{thread_id}/state/{checkpoint_id}
    # The SDK's get_state(checkpoint_id=...) maps to this GET request.
    elog("Testing GET state at checkpoint endpoint", None)
    state_get = await client.threads.get_state(
        thread_id=thread_id, checkpoint_id=checkpoint_id
    )
    elog("GET state response", state_get)

    assert isinstance(state_get, dict)
    assert "values" in state_get
    assert "checkpoint" in state_get
    assert state_get["checkpoint"]["thread_id"] == thread_id
    assert state_get["checkpoint"]["checkpoint_id"] == checkpoint_id
    # Verify content to ensure a valid state was retrieved
    assert "messages" in state_get["values"]
    assert any(m.get("type") == "ai" for m in state_get["values"]["messages"]), (
        "No AI response message found in state"
    )

    # 6. Test POST endpoint: /threads/{thread_id}/state/checkpoint
    # The SDK's get_state(checkpoint=...) maps to this POST request.
    elog("Testing POST state at checkpoint endpoint", None)
    checkpoint_obj: Checkpoint = {
        "thread_id": thread_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_ns": checkpoint_ns,
    }
    state_post = await client.threads.get_state(
        thread_id=thread_id, checkpoint=checkpoint_obj
    )
    elog("POST state response", state_post)

    assert isinstance(state_post, dict)
    assert state_post == state_get, (
        "State from GET and POST endpoints should be identical"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_latest_state_simple_agent_e2e():
    client = get_e2e_client()
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    await client.runs.wait(
        thread_id=thread_id,
        assistant_id="agent",
        input={
            "messages": [
                {
                    "role": "human",
                    "content": "Give me a quick fact about the Eiffel Tower",
                }
            ]
        },
    )

    runs_list = await client.runs.list(thread_id)
    assert runs_list, "Expected run to be created"
    run_info = runs_list[0]
    assert run_info["status"] in ("completed", "interrupted")

    latest_state = await client.threads.get_state(thread_id=thread_id)
    elog("Threads.get_state latest", latest_state)

    assert isinstance(latest_state, dict)
    assert latest_state["checkpoint"]["thread_id"] == thread_id
    assert latest_state["checkpoint"]["checkpoint_id"] is not None
    assert "values" in latest_state and isinstance(latest_state["values"], dict)
    messages = latest_state["values"].get("messages", [])
    assert messages, "Expected messages in latest state"
    assert any(m.get("type") == "ai" for m in messages), "Missing AI reply"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_latest_state_human_in_loop_interrupt_e2e():
    client = get_e2e_client()
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    await client.runs.wait(
        thread_id=thread_id,
        assistant_id="agent_hitl",
        input={
            "messages": [
                {
                    "role": "human",
                    "content": "Please look up the forecast for tomorrow",
                }
            ]
        },
    )

    runs_list = await client.runs.list(thread_id)
    assert runs_list, "Expected run to be created"
    run_info = runs_list[0]
    elog("Run info after wait (HITL)", run_info)
    assert run_info["status"] == "interrupted"

    latest_state = await client.threads.get_state(thread_id=thread_id)
    elog("Threads.get_state latest (HITL)", latest_state)

    assert isinstance(latest_state, dict)
    assert latest_state["checkpoint"]["thread_id"] == thread_id
    history = await client.threads.get_history(thread_id)
    assert history, "Expected history entries for interrupted run"
    recent_checkpoint = history[0]["checkpoint"]
    assert (
        latest_state["checkpoint"]["checkpoint_id"]
        == recent_checkpoint["checkpoint_id"]
    )
    interrupts = latest_state.get("interrupts", [])
    assert interrupts, "Interrupts should be present for interrupted run"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_latest_state_with_subgraphs_e2e():
    client = get_e2e_client()
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    elog("Created thread", thread)

    await client.runs.wait(
        thread_id=thread_id,
        assistant_id="subgraph_hitl_agent",
        input={"foo": "Test value."},
    )

    state_without_subgraphs = await client.threads.get_state(
        thread_id=thread_id,
        subgraphs=False,
    )

    elog("Threads.get_state without subgraphs:", state_without_subgraphs)

    assert "values" not in state_without_subgraphs["tasks"][0]["state"], (
        "Expected subgraph state to be excluded from the response"
    )

    state_with_subgraphs = await client.threads.get_state(
        thread_id=thread_id,
        subgraphs=True,
    )

    elog("Threads.get_state with subgraphs:", state_with_subgraphs)

    assert "values" in state_with_subgraphs["tasks"][0]["state"], (
        "Expected subgraph state to be included in the response"
    )

    assert (
        state_with_subgraphs["tasks"][0]["state"]["values"]["foo"]
        == "Initial subgraph value."
    ), "Expected subgraph state to be included and correct"
