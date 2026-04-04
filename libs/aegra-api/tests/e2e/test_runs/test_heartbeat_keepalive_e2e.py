"""E2E tests for heartbeat keep-alive on join/wait endpoints.

Validates that:
  - join and wait endpoints return chunked application/json responses
  - The LangGraph SDK client can parse the response (heartbeats transparent)
  - Raw httpx streaming reads see heartbeat bytes for slow runs
  - The final JSON output is correct

Requirements:
  - A running Aegra server (``uv run aegra dev`` or ``docker compose up``)
  - The ``agent`` graph deployed in the server's ``aegra.json``
"""

import json

import pytest
from httpx import AsyncClient

from aegra_api.settings import settings
from tests.e2e._utils import check_and_skip_if_geo_blocked, elog, get_e2e_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_assistant_and_thread(sdk: object) -> tuple[str, str]:
    """Create an assistant and thread, return (assistant_id, thread_id)."""
    assistant = await sdk.assistants.create(
        graph_id="agent",
        config={"tags": ["heartbeat-test"]},
        if_exists="do_nothing",
    )
    thread = await sdk.threads.create()
    return assistant["assistant_id"], thread["thread_id"]


# ---------------------------------------------------------------------------
# GET /threads/{thread_id}/runs/{run_id}/join — SDK client
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_join_returns_output_via_sdk() -> None:
    """SDK client.runs.join() works transparently with heartbeat responses."""
    sdk = get_e2e_client()
    assistant_id, thread_id = await _create_assistant_and_thread(sdk)

    # Create a background run
    run = await sdk.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello in one word."}]},
    )
    elog("Runs.create", run)
    run_id = run["run_id"]

    # Join — SDK internally uses request_reconnect which handles chunked reads
    output = await sdk.runs.join(thread_id, run_id)
    elog("Runs.join output", output)

    assert isinstance(output, dict), f"Expected dict, got {type(output)}"
    assert output != {}, "Join should return non-empty output"

    # Verify run completed successfully
    run_details = await sdk.runs.get(thread_id, run_id)
    check_and_skip_if_geo_blocked(run_details)
    assert run_details["status"] == "success"


# ---------------------------------------------------------------------------
# GET /threads/{thread_id}/runs/{run_id}/join — raw HTTP
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_join_returns_chunked_json_via_http() -> None:
    """Raw HTTP streaming read sees application/json with valid JSON body."""
    sdk = get_e2e_client()
    assistant_id, thread_id = await _create_assistant_and_thread(sdk)

    run = await sdk.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say hi."}]},
    )
    run_id = run["run_id"]

    async with (
        AsyncClient(base_url=settings.app.SERVER_URL, timeout=120.0) as http,
        http.stream("GET", f"/threads/{thread_id}/runs/{run_id}/join") as resp,
    ):
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

        # Read all chunks
        chunks: list[bytes] = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)

    elog("Join chunks", {"count": len(chunks), "sizes": [len(c) for c in chunks]})

    # Concatenated body should be valid JSON
    full_body = b"".join(chunks)
    output = json.loads(full_body)
    elog("Join parsed output", output)

    assert isinstance(output, dict)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_join_terminal_run_returns_immediately() -> None:
    """Joining an already-completed run returns JSON with no heartbeat overhead."""
    sdk = get_e2e_client()
    assistant_id, thread_id = await _create_assistant_and_thread(sdk)

    # Create and wait for completion via SDK
    run = await sdk.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={"messages": [{"role": "user", "content": "Say yes."}]},
    )
    run_id = run["run_id"]

    # Wait for it to finish first
    await sdk.runs.join(thread_id, run_id)

    # Now join again — should return immediately (no heartbeats needed)
    async with (
        AsyncClient(base_url=settings.app.SERVER_URL, timeout=10.0) as http,
        http.stream("GET", f"/threads/{thread_id}/runs/{run_id}/join") as resp,
    ):
        assert resp.status_code == 200
        chunks: list[bytes] = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)

    full_body = b"".join(chunks)
    output = json.loads(full_body)

    elog("Join terminal output", output)
    assert isinstance(output, dict)
    # No heartbeats expected for terminal runs; HTTP buffering may split the
    # single JSON payload into multiple network chunks, so assert >= 1.
    assert len(chunks) >= 1, f"Terminal run should return at least 1 chunk, got {len(chunks)}"


# ---------------------------------------------------------------------------
# POST /threads/{thread_id}/runs/wait — SDK client
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_wait_returns_output_via_sdk() -> None:
    """SDK client wait endpoint works with heartbeat streaming."""
    sdk = get_e2e_client()
    assistant_id, thread_id = await _create_assistant_and_thread(sdk)

    output = await sdk.runs.wait(
        thread_id,
        assistant_id,
        input={"messages": [{"role": "user", "content": "Say hello in one word."}]},
    )
    elog("Runs.wait output", output)

    assert isinstance(output, dict)
    assert output != {}, "Wait should return non-empty output"


# ---------------------------------------------------------------------------
# POST /threads/{thread_id}/runs/wait — raw HTTP
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_wait_returns_chunked_json_via_http() -> None:
    """Raw HTTP streaming read of /runs/wait returns valid JSON."""
    sdk = get_e2e_client()
    assistant_id, thread_id = await _create_assistant_and_thread(sdk)

    async with (
        AsyncClient(base_url=settings.app.SERVER_URL, timeout=120.0) as http,
        http.stream(
            "POST",
            f"/threads/{thread_id}/runs/wait",
            json={
                "assistant_id": assistant_id,
                "input": {"messages": [{"role": "user", "content": "Say hi."}]},
            },
        ) as resp,
    ):
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

        # Check for Location header (reconnect support)
        assert "location" in resp.headers, "Expected Location header for reconnect"

        chunks: list[bytes] = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)

    elog("Wait chunks", {"count": len(chunks), "sizes": [len(c) for c in chunks]})

    full_body = b"".join(chunks)
    output = json.loads(full_body)
    elog("Wait parsed output", output)

    assert isinstance(output, dict)
    assert output != {}


# ---------------------------------------------------------------------------
# POST /runs/wait — stateless
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stateless_wait_returns_chunked_json() -> None:
    """POST /runs/wait (stateless) returns valid chunked JSON."""
    sdk = get_e2e_client()

    assistant = await sdk.assistants.create(
        graph_id="agent",
        config={"tags": ["heartbeat-stateless"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]

    async with (
        AsyncClient(base_url=settings.app.SERVER_URL, timeout=120.0) as http,
        http.stream(
            "POST",
            "/runs/wait",
            json={
                "assistant_id": assistant_id,
                "input": {"messages": [{"role": "user", "content": "Say hi."}]},
            },
        ) as resp,
    ):
        assert resp.status_code == 200

        chunks: list[bytes] = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)

    full_body = b"".join(chunks)
    output = json.loads(full_body)
    elog("Stateless wait output", output)

    assert isinstance(output, dict)
    assert output != {}


# ---------------------------------------------------------------------------
# Heartbeat wire-level proof — slow agent
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_heartbeat_bytes_visible_with_slow_agent() -> None:
    """Prove heartbeat newlines are actually sent on the wire.

    Uses the stress_test graph (no LLM, deterministic delay) with a 15s total
    run time. With a 5s keepalive interval, at least 2 heartbeat chunks must
    appear before the final JSON chunk.
    """
    sdk = get_e2e_client()

    assistant = await sdk.assistants.create(
        graph_id="stress_test",
        config={"tags": ["heartbeat-proof"]},
        if_exists="do_nothing",
    )
    assistant_id = assistant["assistant_id"]
    thread = await sdk.threads.create()
    thread_id = thread["thread_id"]

    async with (
        AsyncClient(base_url=settings.app.SERVER_URL, timeout=120.0) as http,
        http.stream(
            "POST",
            f"/threads/{thread_id}/runs/wait",
            json={
                "assistant_id": assistant_id,
                "input": {
                    "messages": [{"role": "user", "content": json.dumps({"delay": 3.0, "steps": 5})}],
                },
            },
        ) as resp,
    ):
        assert resp.status_code == 200

        chunks: list[bytes] = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)

    heartbeats = [c for c in chunks if c == b"\n"]
    json_chunks = [c for c in chunks if c != b"\n"]

    elog(
        "Heartbeat proof",
        {
            "total_chunks": len(chunks),
            "heartbeats": len(heartbeats),
            "json_chunks": len(json_chunks),
        },
    )

    # Calculate expected heartbeats based on actual keepalive interval setting
    expected_runtime = 3.0 * 5  # delay_per_step * num_steps
    min_heartbeats = max(1, int(expected_runtime / settings.app.KEEPALIVE_INTERVAL_SECS) - 1)
    assert len(heartbeats) >= min_heartbeats, (
        f"Expected at least {min_heartbeats} heartbeat(s) for ~{expected_runtime}s run "
        f"with {settings.app.KEEPALIVE_INTERVAL_SECS}s interval, got {len(heartbeats)}"
    )
    assert len(json_chunks) >= 1, "Expected at least 1 JSON chunk"

    full_body = b"".join(chunks)
    output = json.loads(full_body)
    assert isinstance(output, dict)

    # Verify the stress_test graph completed correctly
    ai_content = json.loads(output["messages"][-1]["content"])
    assert ai_content["steps_completed"] == 5
    assert ai_content["status"] == "completed"
