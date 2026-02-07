import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_assistant_versions():
    """
    Test that updating an assistant creates a new version and both versions are retrievable.
    """
    client = get_e2e_client()

    # 1. Create assistant
    assistant = await client.assistants.create(
        name="Test",
        description="Test Assistant",
        graph_id="agent",
        context={"max_search_results": 3},
        if_exists="do_nothing",
    )

    # 2. Patch assistant to create a new version
    updated_assistant = await client.assistants.update(
        name="Test-Updated",
        description="Updated Test Assistant",
        graph_id="agent",
        assistant_id=assistant["assistant_id"],
        context={"max_search_results": 5},
    )

    # 3. Verify version incremented
    assert updated_assistant["version"] == assistant["version"] + 1
    elog(
        "Assistant version updated successfully",
        {
            "assistant_id": assistant["assistant_id"],
            "old_version": assistant["version"],
            "new_version": updated_assistant["version"],
        },
    )

    # 4. Verify both versions exist
    assistant_versions = await client.assistants.get_versions(assistant_id=assistant["assistant_id"])
    assert len(assistant_versions) == 2

    elog(
        "Both assistant versions exist",
        {"assistant_id": assistant["assistant_id"], "versions": assistant_versions},
    )

    # Clean up
    await client.assistants.delete(assistant_id=assistant["assistant_id"])

    # Check if assistant is deleted
    with pytest.raises(Exception):  # noqa: B017 - SDK doesn't expose specific exception type
        assistant = await client.assistants.get(assistant_id=assistant["assistant_id"])


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_change_assistant_version():
    """
    Test that we can set the assistant to a previous version.
    """
    client = get_e2e_client()

    # 1. Create assistant
    assistant = await client.assistants.create(
        name="Test",
        description="Test Assistant",
        graph_id="agent",
        context={"max_search_results": 3},
        if_exists="do_nothing",
    )

    # 2. Patch assistant to create a new version
    await client.assistants.update(
        name="Test-Updated",
        description="Updated Test Assistant",
        graph_id="agent",
        assistant_id=assistant["assistant_id"],
        context={"max_search_results": 5},
    )

    set_latest_version = 1

    latest_assistant = await client.assistants.set_latest(
        assistant_id=assistant["assistant_id"], version=set_latest_version
    )
    assert latest_assistant["name"] == assistant["name"]
    assert latest_assistant["version"] == set_latest_version

    elog(
        "Assistant version set successfully",
        {
            "assistant_id": assistant["assistant_id"],
            "set_version": set_latest_version,
            "latest_assistant": latest_assistant,
        },
    )

    # Clean up
    await client.assistants.delete(assistant_id=assistant["assistant_id"])
    # Check if assistant is deleted
    with pytest.raises(Exception):  # noqa: B017 - SDK doesn't expose specific exception type
        assistant = await client.assistants.get(assistant_id=assistant["assistant_id"])
