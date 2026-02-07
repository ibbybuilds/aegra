import pytest

from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client


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

    # Check for geo-block before asserting status
    check_and_skip_if_geo_blocked(run_info)

    assert run_info["status"] in ("success", "interrupted")

    latest_state = await client.threads.get_state(thread_id=thread_id)
    elog("Threads.get_state latest", latest_state)

    assert isinstance(latest_state, dict)
    assert latest_state["checkpoint"]["thread_id"] == thread_id
    assert latest_state["checkpoint"]["checkpoint_id"] is not None
    assert "values" in latest_state and isinstance(latest_state["values"], dict)
    messages = latest_state["values"].get("messages", [])

    # If run succeeded, check messages. If it failed (but not blocked?), skip message check
    if run_info["status"] == "success":
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

    # Check for geo-block
    check_and_skip_if_geo_blocked(run_info)

    assert run_info["status"] == "interrupted"

    latest_state = await client.threads.get_state(thread_id=thread_id)
    elog("Threads.get_state latest (HITL)", latest_state)

    assert isinstance(latest_state, dict)
    assert latest_state["checkpoint"]["thread_id"] == thread_id
    history = await client.threads.get_history(thread_id)
    assert history, "Expected history entries for interrupted run"
    recent_checkpoint = history[0]["checkpoint"]
    assert latest_state["checkpoint"]["checkpoint_id"] == recent_checkpoint["checkpoint_id"]
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

    # Check if run failed due to block (implicitly via getting runs)
    runs = await client.runs.list(thread_id)
    if runs:
        check_and_skip_if_geo_blocked(runs[0])

    state_without_subgraphs = await client.threads.get_state(
        thread_id=thread_id,
        subgraphs=False,
    )

    elog("Threads.get_state without subgraphs:", state_without_subgraphs)

    # Combined nested if statements into a single line
    if runs and runs[0]["status"] == "success" and state_without_subgraphs.get("tasks"):
        assert "values" not in state_without_subgraphs["tasks"][0]["state"], (
            "Expected subgraph state to be excluded from the response"
        )

    state_with_subgraphs = await client.threads.get_state(
        thread_id=thread_id,
        subgraphs=True,
    )

    elog("Threads.get_state with subgraphs:", state_with_subgraphs)

    if runs and runs[0]["status"] == "success" and state_with_subgraphs.get("tasks"):
        assert "values" in state_with_subgraphs["tasks"][0]["state"], (
            "Expected subgraph state to be included in the response"
        )

        assert state_with_subgraphs["tasks"][0]["state"]["values"]["foo"] == "Initial subgraph value.", (
            "Expected subgraph state to be included and correct"
        )

    await client.runs.wait(
        thread_id=thread_id,
        assistant_id="subgraph_hitl_agent",
        command={"resume": "Resume test value."},
    )

    # Check resume status
    resume_runs = await client.runs.list(thread_id)
    if resume_runs:
        check_and_skip_if_geo_blocked(resume_runs[0])

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
