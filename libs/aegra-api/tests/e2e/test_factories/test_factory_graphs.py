"""E2E tests for the unified factory example.

Tests verify that the ``factory`` graph is detected, loaded per-request, and
produces valid agent responses when invoked through the full server stack.
Each test exercises a different ``FactoryContext`` field to prove that typed
context drives model selection, graph structure changes, and system prompt
customisation.
"""

import pytest

from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client

# ---------------------------------------------------------------------------
# Default context — factory works with no explicit context
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_runs_with_default_context() -> None:
    """Factory should build a graph and respond using default FactoryContext values."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-default"]},
        if_exists="do_nothing",
    )
    elog("Factory default assistant", assistant)
    assert "assistant_id" in assistant

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hello in one word."}]},
    )
    elog("Factory default run", run)
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Factory default final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"
    assert isinstance(final_state, dict)
    assert len(final_state.get("messages", [])) >= 1


# ---------------------------------------------------------------------------
# Model override via context
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_model_override_via_context() -> None:
    """Passing ``context={"model": "openai/gpt-4o"}`` should use that model.

    The default model is ``openai/gpt-4o-mini``. This test overrides it with
    ``openai/gpt-4o`` and verifies the response metadata reflects the
    overridden model.
    """
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-model-override"]},
        if_exists="do_nothing",
    )
    elog("Factory model override assistant", assistant)

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Reply with just the word 'yes'."}]},
        context={"model": "openai/gpt-4o"},
    )
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Factory model override final state", final_state)

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
# Search disabled — graph has no tools node
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_search_disabled_via_context() -> None:
    """With ``enable_search=False`` the graph has no tools node and still runs."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-no-search"]},
        if_exists="do_nothing",
    )

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hi."}]},
        context={"enable_search": False},
    )
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Factory no-search final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"
    assert len(final_state.get("messages", [])) >= 1


# ---------------------------------------------------------------------------
# Custom system prompt
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_custom_system_prompt() -> None:
    """Passing a custom ``system_prompt`` should influence the agent's behaviour."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-prompt"]},
        if_exists="do_nothing",
    )

    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "user", "content": "Say hello."}]},
        context={
            "system_prompt": "Always respond in French. Never use English.",
        },
    )
    run_id = run["run_id"]

    final_state = await client.runs.join(thread_id, run_id)
    elog("Factory custom prompt final state", final_state)

    check_run = await client.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(check_run)

    assert check_run["status"] == "success"

    messages = final_state.get("messages", [])
    assert len(messages) >= 1
    ai_text = messages[-1].get("content", "").lower()
    elog("AI response text", ai_text)
    # The model should respond in French (bonjour, salut, etc.)
    french_indicators = ["bonjour", "salut", "coucou", "bienvenue", "enchant"]
    assert any(word in ai_text for word in french_indicators), f"Expected French response, got: {ai_text}"


# ---------------------------------------------------------------------------
# Streaming support
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_streams_messages() -> None:
    """Streaming should work with the unified factory graph."""
    client = get_e2e_client()

    assistant = await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-stream"]},
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


# ---------------------------------------------------------------------------
# Factory graph discovery — assistants API should list the factory graph_id
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_factory_appears_in_assistants_search() -> None:
    """The ``factory`` graph_id should be discoverable via the assistants API."""
    client = get_e2e_client()

    await client.assistants.create(
        graph_id="factory",
        config={"tags": ["e2e", "factory-discovery"]},
        if_exists="do_nothing",
    )

    all_assistants = await client.assistants.search(limit=100)
    graph_ids = {a["graph_id"] for a in all_assistants}
    elog("All graph_ids in assistants", sorted(graph_ids))

    assert "factory" in graph_ids, "factory not found in assistants"
