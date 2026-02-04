import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_deletion_with_active_runs():
    """
    Test that deleting an assistant with active runs works via SDK.

    The API should automatically cancel active runs and delete the assistant.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["assistant-deletion-active-runs"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # 2. Create an active run
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Process this"}]},
    )
    run_id = run["run_id"]

    elog("Created assistant run", {"assistant_id": assistant_id, "run_id": run_id})

    # 3. Delete assistant
    await client.assistants.delete(assistant_id)
    elog("Deleted assistant", {"assistant_id": assistant_id})

    # 4. Verify assistant is deleted
    try:
        await client.assistants.get(assistant_id)
        pytest.fail("Assistant should have been deleted but still exists")
    except Exception:
        pass

    # 5. Verify run is also deleted/cancelled
    runs_list = await client.runs.list(thread_id)
    assert all(r["assistant_id"] != assistant_id for r in runs_list), (
        "Run should have been deleted/cancelled when assistant was deleted"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_deletion_with_completed_runs():
    """
    Test that deleting an assistant with completed runs works via SDK.

    Completed runs should not block assistant deletion, and runs should be removed.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["assistant-deletion-completed-runs"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # 2. Create and complete a run
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello"}]},
    )
    run_id = run["run_id"]

    # Wait until run finishes
    await client.runs.join(thread_id, run_id)

    # 3. Delete assistant
    await client.assistants.delete(assistant_id)
    elog("Deleted assistant with completed runs", {"assistant_id": assistant_id})

    # 4. Verify assistant is deleted
    try:
        await client.assistants.get(assistant_id)
        pytest.fail("Assistant should have been deleted but still exists")
    except Exception:
        pass

    # 5. Verify run is also deleted
    runs_list = await client.runs.list(thread_id)
    assert all(r["assistant_id"] != assistant_id for r in runs_list)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_deletion_no_runs():
    """
    Test that deleting an assistant without runs works via SDK.
    """
    client = get_e2e_client()

    # 1. Create assistant
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["assistant-deletion-no-runs"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    # 2. Delete assistant
    await client.assistants.delete(assistant_id)
    elog("Deleted assistant without runs", {"assistant_id": assistant_id})

    # 3. Verify assistant is deleted
    try:
        await client.assistants.get(assistant_id)
        pytest.fail("Assistant should have been deleted but still exists")
    except Exception:
        pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_deletion_multiple_runs():
    """
    Test that deleting an assistant with multiple runs (active + completed)
    cancels/removes all associated runs.
    """
    client = get_e2e_client()

    # 1. Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["assistant-deletion-multiple-runs"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # 2. Create multiple runs
    run1 = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Run 1"}]},
    )
    run2 = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Run 2"}]},
    )

    elog(
        "Created multiple runs for assistant",
        {
            "assistant_id": assistant_id,
            "run1_id": run1["run_id"],
            "run2_id": run2["run_id"],
        },
    )

    # 3. Delete assistant
    await client.assistants.delete(assistant_id)
    elog("Deleted assistant with multiple runs", {"assistant_id": assistant_id})

    # 4. Verify assistant is deleted
    try:
        await client.assistants.get(assistant_id)
        pytest.fail("Assistant should have been deleted but still exists")
    except Exception:
        pass

    # 5. Verify all runs tied to assistant are deleted
    runs_list = await client.runs.list(thread_id)
    assert all(r["assistant_id"] != assistant_id for r in runs_list)
