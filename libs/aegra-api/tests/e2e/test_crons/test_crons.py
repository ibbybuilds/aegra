"""E2E tests for cron job endpoints.

Covers all six SDK operations consumed by ``CronClient``:
    create (stateless), create_for_thread, update, delete, search, count.

Tests run against a live server (CRON_ENABLED is not required; the scheduler
is only needed for scheduled firing — these tests only verify the CRUD API).
"""

import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cron_stateless_create_and_delete() -> None:
    """Create a stateless cron, verify the first Run is returned, then delete it."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["e2e-cron-stateless"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]
    elog("Assistant", assistant)

    cron_run = await client.crons.create(
        assistant_id,
        schedule="0 3 * * *",  # 03:00 UTC every day — won't fire during test
        input={"messages": [{"role": "user", "content": "cron check"}]},
    )
    elog("Cron.create (stateless)", cron_run)

    # SDK returns a Run object on create
    assert "run_id" in cron_run
    cron_id = cron_run.get("cron_id")
    assert cron_id is not None, "cron_id must be present in the Run response"

    # Clean up — must not raise
    await client.crons.delete(cron_id)
    elog("Cron deleted", {"cron_id": cron_id})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cron_for_thread_create_and_delete() -> None:
    """Create a thread-bound cron, verify the Run is returned, then delete."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["e2e-cron-thread"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    elog("Thread", thread)

    cron_run = await client.crons.create_for_thread(
        thread_id,
        assistant_id,
        schedule="0 4 * * *",  # 04:00 UTC every day
        input={"messages": [{"role": "user", "content": "thread cron check"}]},
    )
    elog("Cron.create_for_thread", cron_run)

    assert "run_id" in cron_run
    cron_id = cron_run.get("cron_id")
    assert cron_id is not None

    await client.crons.delete(cron_id)
    elog("Cron deleted", {"cron_id": cron_id})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cron_search_and_count() -> None:
    """Create two crons, search and count them by assistant_id, then clean up."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["e2e-cron-search"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    run_a = await client.crons.create(
        assistant_id,
        schedule="0 5 * * *",
        input={"messages": [{"role": "user", "content": "cron A"}]},
    )
    run_b = await client.crons.create(
        assistant_id,
        schedule="0 6 * * *",
        input={"messages": [{"role": "user", "content": "cron B"}]},
    )
    cron_id_a = run_a["cron_id"]
    cron_id_b = run_b["cron_id"]
    elog("Created crons", {"a": cron_id_a, "b": cron_id_b})

    try:
        # search
        crons = await client.crons.search(assistant_id=assistant_id)
        elog("Cron.search", crons)
        found_ids = {c["cron_id"] for c in crons}
        assert cron_id_a in found_ids
        assert cron_id_b in found_ids

        # count
        total = await client.crons.count(assistant_id=assistant_id)
        elog("Cron.count", total)
        assert total >= 2
    finally:
        await client.crons.delete(cron_id_a)
        await client.crons.delete(cron_id_b)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cron_update() -> None:
    """Create a cron, update its schedule and enabled flag, verify the response."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["e2e-cron-update"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    cron_run = await client.crons.create(
        assistant_id,
        schedule="0 7 * * *",
        input={"messages": [{"role": "user", "content": "before update"}]},
    )
    cron_id = cron_run["cron_id"]
    elog("Created cron", {"cron_id": cron_id})

    try:
        updated = await client.crons.update(
            cron_id,
            schedule="0 8 * * *",
            enabled=False,
        )
        elog("Cron.update", updated)

        assert updated["cron_id"] == cron_id
        assert updated["schedule"] == "0 8 * * *"
        assert updated["enabled"] is False
    finally:
        await client.crons.delete(cron_id)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cron_with_timezone() -> None:
    """Create a cron with an IANA timezone; verify the timezone is stored in payload."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["e2e-cron-timezone"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    cron_run = await client.crons.create(
        assistant_id,
        schedule="0 9 * * *",
        timezone="America/New_York",
        input={"messages": [{"role": "user", "content": "timezone cron"}]},
    )
    cron_id = cron_run["cron_id"]
    elog("Created cron with timezone", {"cron_id": cron_id})

    try:
        # Verify via search
        crons = await client.crons.search(assistant_id=assistant_id)
        matching = [c for c in crons if c["cron_id"] == cron_id]
        assert len(matching) == 1
        stored_payload = matching[0].get("payload", {})
        elog("Stored payload", stored_payload)
        assert stored_payload.get("timezone") == "America/New_York"
    finally:
        await client.crons.delete(cron_id)
