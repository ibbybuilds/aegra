import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_latest_state_simple_agent_e2e():
    """Test get_state for a simple agent run, verifying checkpoint and AI response data."""
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
    assert run_info["status"] in ("success", "interrupted")

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
    """Test get_state for interrupted HITL agent, verifying interrupt data and checkpoint alignment."""
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
    """Test get_state subgraph parameter behavior, verifying inclusion/exclusion of subgraph state."""
    client = get_e2e_client()
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    elog("Created thread", thread)

    # Use graph_id directly - should be auto-created from aegra.json
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

    await client.runs.wait(
        thread_id=thread_id,
        assistant_id="subgraph_hitl_agent",
        command={"resume": "Resume test value."},
    )

    state_with_subgraphs_after_resume = await client.threads.get_state(
        thread_id=thread_id,
        subgraphs=True,
    )

    elog(
        "Threads.get_state with subgraphs after resume:",
        state_with_subgraphs_after_resume,
    )

    assert state_with_subgraphs_after_resume["tasks"] == [], (
        "Expected subgraph state to be excluded from the response after resume"
    )
