import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_thread_deletion_with_active_runs():
    """
    Test that thread deletion with active runs works seamlessly via SDK.

    The API should automatically cancel active runs and delete the thread.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["thread-deletion-active-runs"]},
        if_exists="do_nothing",
    )
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    elog(
        "Created thread and assistant",
        {"thread_id": thread_id, "assistant_id": assistant_id},
    )

    # 2. Create an active run
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Start processing"}]},
    )
    run_id = run["run_id"]

    elog("Created run", {"run_id": run_id, "status": run["status"]})

    # 3. Verify run exists and is active
    runs_list = await client.runs.list(thread_id)
    assert len(runs_list) >= 1
    active_run = next(r for r in runs_list if r["run_id"] == run_id)
    assert active_run["status"] in ["pending", "running"]

    # 4. Delete thread via SDK - should work seamlessly
    await client.threads.delete(thread_id)
    elog("Thread deleted successfully via SDK", {"thread_id": thread_id})

    # 5. Verify thread is actually deleted
    try:
        await client.threads.get(thread_id)
        pytest.fail("Thread should have been deleted but still exists")
    except Exception:
        # Expected - thread should be gone
        elog("Thread properly deleted (404 as expected)", {"thread_id": thread_id})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_thread_deletion_with_completed_runs():
    """
    Test that thread deletion with completed runs works via SDK.

    Completed runs should not interfere with thread deletion.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["thread-deletion-completed-runs"]},
        if_exists="do_nothing",
    )
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # 2. Create and complete a run
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello"}]},
    )
    run_id = run["run_id"]

    # 3. Wait for run to complete
    final_state = await client.runs.join(thread_id, run_id)
    elog(
        "Run completed",
        {"final_state_keys": list(final_state.keys()) if final_state else None},
    )

    # 4. Verify run is completed
    completed_run = await client.runs.get(thread_id, run_id)
    assert completed_run["status"] in ("success", "error")
    elog("Run status verified", {"status": completed_run["status"]})

    # 5. Delete thread via SDK - should work fine
    await client.threads.delete(thread_id)
    elog("Thread with completed runs deleted successfully", {"thread_id": thread_id})

    # 6. Verify thread is deleted
    try:
        await client.threads.get(thread_id)
        pytest.fail("Thread should have been deleted but still exists")
    except Exception:
        # Expected - thread should be gone
        pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_thread_deletion_empty_thread():
    """
    Test that deleting empty threads works via SDK.

    This is the baseline case - should always work.
    """
    client = get_e2e_client()

    # 1. Create empty thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    elog("Created empty thread", {"thread_id": thread_id})

    # 2. Verify no runs exist
    runs_list = await client.runs.list(thread_id)
    assert len(runs_list) == 0
    # 3. Delete thread via SDK
    await client.threads.delete(thread_id)
    elog("Empty thread deleted successfully", {"thread_id": thread_id})

    # 4. Verify thread is deleted
    try:
        await client.threads.get(thread_id)
        pytest.fail("Thread should have been deleted but still exists")
    except Exception:
        # Expected - thread should be gone
        pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_thread_deletion_multiple_runs():
    """
    Test that thread deletion works with multiple runs (active and completed).

    Should cancel all active runs and delete the thread.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["thread-deletion-multiple-runs"]},
        if_exists="do_nothing",
    )
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # 2. Create multiple runs
    run1 = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "First run"}]},
    )

    run2 = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Second run"}]},
    )

    elog(
        "Created multiple runs", {"run1_id": run1["run_id"], "run2_id": run2["run_id"]}
    )

    # 3. Verify multiple runs exist
    runs_list = await client.runs.list(thread_id)
    assert len(runs_list) >= 2
    # 4. Delete thread via SDK - should cancel all runs and delete thread
    await client.threads.delete(thread_id)
    elog("Thread with multiple runs deleted successfully", {"thread_id": thread_id})

    # 5. Verify thread is deleted
    try:
        await client.threads.get(thread_id)
        pytest.fail("Thread should have been deleted but still exists")
    except Exception:
        # Expected - thread should be gone
        pass
