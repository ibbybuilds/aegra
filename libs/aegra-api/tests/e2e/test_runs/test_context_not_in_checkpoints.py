"""E2E regression test: context must not leak into checkpoint metadata (issue #247).

A run created with a `context` payload (e.g. a JWT token) must not have that
data stored in the LangGraph checkpoint's configurable field, which would
expose sensitive information via GET /threads/{id}/history.
"""

import pytest

from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client

_SECRET_KEY = "secret"
_SECRET_VALUE = "should-not-persist"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_context_does_not_leak_into_checkpoint_metadata() -> None:
    """Verify that run context is not stored inside checkpoint configurable.

    Steps:
    1. Create an assistant + thread.
    2. Create a run with context: {_SECRET_KEY: _SECRET_VALUE}.
    3. Wait for run to finish.
    4. Fetch thread history via the SDK.
    5. Assert that _SECRET_VALUE does not appear in any checkpoint.
    """
    client = get_e2e_client()

    # 1) Ensure assistant exists
    assistant = await client.assistants.create(
        graph_id="agent",
        config={},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)
    assert "assistant_id" in assistant
    assistant_id = assistant["assistant_id"]

    # 2) Create a fresh thread for isolation
    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]

    # 3) Create a run with sensitive context
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello."}]},
        context={_SECRET_KEY: _SECRET_VALUE},
    )
    elog("Runs.create", run)
    assert "run_id" in run
    run_id = run["run_id"]

    # 4) Wait for completion
    await client.runs.join(thread_id, run_id)

    # Check for geo-blocking before asserting results
    finished_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(finished_run)

    # 5) Fetch thread checkpoint history
    history = await client.threads.get_history(thread_id)
    elog("Threads.get_history", history)
    assert isinstance(history, list), "Expected history to be a list"

    # 6) Assert secret does not appear in any checkpoint's configurable
    for checkpoint in history:
        config = checkpoint.get("config", {}) if isinstance(checkpoint, dict) else {}
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        assert _SECRET_VALUE not in str(configurable), (
            f"Secret value '{_SECRET_VALUE}' was found in checkpoint configurable: {configurable}"
        )
