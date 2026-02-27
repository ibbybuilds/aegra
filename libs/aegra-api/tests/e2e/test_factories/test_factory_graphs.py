"""E2E tests for graph factory examples.

Tests verify that factory graphs are detected, loaded per-request, and produce
valid agent responses when invoked through the full server stack.
"""

import pytest

from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client

# ---------------------------------------------------------------------------
# Config factory (model selection via config["configurable"]["model"])
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_config_factory_runs_with_default_model() -> None:
    """Config factory should build a graph and respond using the default model."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="config_factory",
        config={"tags": ["e2e", "config-factory"]},
        if_exists="do_nothing",
    )
    elog("Config factory assistant", assistant)
    assert "assistant_id" in assistant

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hello in one word."}]},
    )
    elog("Config factory run", run)
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Config factory final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"
    assert isinstance(final_state, dict)
    assert len(final_state.get("messages", [])) >= 1  # at least the AI response


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_config_factory_applies_model_override() -> None:
    """Config factory should use an overridden model instead of the default.

    The default model is ``openai/gpt-4o-mini``. This test overrides it with
    ``openai/gpt-4o`` and verifies the response metadata reflects the
    overridden model.
    """
    client = get_e2e_client()

    override_model = "openai/gpt-4o"

    assistant = await client.assistants.create(
        graph_id="config_factory",
        config={
            "tags": ["e2e", "config-factory-override"],
            "configurable": {"model": override_model},
        },
        if_exists="do_nothing",
    )
    elog("Config factory override assistant", assistant)

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Reply with just the word 'yes'."}]},
    )
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Config factory override final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"
    assert len(final_state.get("messages", [])) >= 1

    # Verify the override was applied by checking response metadata
    messages = final_state.get("messages", [])
    ai_message = messages[-1]
    response_metadata = ai_message.get("response_metadata", {})
    model_name = response_metadata.get("model_name", "")
    elog("Response model_name", model_name)
    assert "gpt-4o" in model_name, f"Expected gpt-4o model, got: {model_name}"
    assert "gpt-4o-mini" not in model_name, f"Expected overridden model (gpt-4o), got default: {model_name}"


# ---------------------------------------------------------------------------
# Runtime factory (user-aware agent with per-user tool access)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_runtime_factory_runs_without_auth() -> None:
    """Runtime factory should work without auth (user=None, public tools only)."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="runtime_factory",
        config={"tags": ["e2e", "runtime-factory"]},
        if_exists="do_nothing",
    )
    elog("Runtime factory assistant", assistant)
    assert "assistant_id" in assistant

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hello in one word."}]},
    )
    elog("Runtime factory run", run)
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Runtime factory final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"
    assert isinstance(final_state, dict)
    assert len(final_state.get("messages", [])) >= 1  # at least the AI response


# ---------------------------------------------------------------------------
# Factory graph discovery — assistants API should list factory graph IDs
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_graphs_appear_in_assistants_search() -> None:
    """Factory graph_ids should be discoverable via the assistants API."""
    client = get_e2e_client()

    # Create assistants for both factory types
    for graph_id in ("config_factory", "runtime_factory"):
        await client.assistants.create(
            graph_id=graph_id,
            config={"tags": ["e2e", "factory-discovery"]},
            if_exists="do_nothing",
        )

    # Search and verify both exist
    all_assistants = await client.assistants.search(limit=100)
    graph_ids = {a["graph_id"] for a in all_assistants}
    elog("All graph_ids in assistants", sorted(graph_ids))

    assert "config_factory" in graph_ids, "config_factory not found in assistants"
    assert "runtime_factory" in graph_ids, "runtime_factory not found in assistants"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_config_factory_streams_messages() -> None:
    """Config factory should support streaming responses."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="config_factory",
        config={"tags": ["e2e", "config-factory-stream"]},
        if_exists="do_nothing",
    )

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    events: list[dict] = []
    async for chunk in client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hi."}]},
        stream_mode="updates",
    ):
        events.append(chunk)

    elog("Stream events count", len(events))
    assert len(events) > 0, "Expected at least one stream event from factory graph"
