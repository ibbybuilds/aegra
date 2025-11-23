import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_run_join_returns_actual_output():
    """
    Test that the join endpoint returns actual run output instead of empty dict.

    This test validates the fix where final_output was being captured correctly
    but then ignored when saving to database (hardcoded as output={}).

    Before fix: join always returned {}
    After fix: join returns the actual graph execution output
    """
    client = get_e2e_client()

    # Create assistant
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["join-output-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    assistant_id = assistant["assistant_id"]

    # Create thread
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # Create run that should produce meaningful output
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello"}]},
        stream_mode=["values"],  # Request values mode to capture final output
    )
    elog("Runs.create", run)
    run_id = run["run_id"]

    # Join the run and get final output
    final_output = await client.runs.join(thread_id, run_id)
    elog("Runs.join final_output", final_output)

    # Verify output is not empty (the main fix)
    assert final_output is not None, "Final output should not be None"
    assert final_output != {}, (
        "Final output should not be empty dict - this was the bug!"
    )

    # The output should be a dict containing the final state
    assert isinstance(final_output, dict), (
        f"Expected dict output, got {type(final_output)}"
    )

    # Verify the run details also show the correct output
    run_details = await client.runs.get(thread_id, run_id)
    elog("Runs.get details", run_details)

    assert run_details["status"] == "success", (
        f"Expected success status, got {run_details['status']}"
    )
    assert run_details["output"] is not None, (
        "Run output should not be None in database"
    )
    assert run_details["output"] != {}, (
        "Run output should not be empty dict in database"
    )

    # Verify join and get return the same output
    assert final_output == run_details["output"], (
        "Join output should match stored run output"
    )

    elog(
        "✅ Test passed - join now returns actual output instead of empty dict!",
        {
            "output_type": type(final_output).__name__,
            "output_empty": final_output == {},
            "output_keys": list(final_output.keys())
            if isinstance(final_output, dict)
            else "not_dict",
        },
    )
