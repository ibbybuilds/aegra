"""Multi-instance E2E tests for worker architecture.

These tests require the multi-instance Docker Compose setup:
  cd aegra
  docker compose -f deployments/test/docker-compose.multi.yml up -d --build
  uv run python libs/aegra-api/tests/e2e/multi_instance/test_multi_instance.py

Tests exercise scenarios that CANNOT be caught by single-instance tests:
  - Cross-instance run creation and join
  - Cross-instance cancel propagation
  - Worker crash recovery via lease reaper
  - SSE stream reconnection to a different instance
  - Concurrent runs distributed across instances
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:2026"
ASSISTANT_ID = "agent"
TIMEOUT = httpx.Timeout(60.0, read=120.0)

_REPO_ROOT = Path(__file__).resolve().parents[5]
COMPOSE_DIR = str(_REPO_ROOT / "deployments" / "test")
COMPOSE_FILE = "docker-compose.multi.yml"


def log(title: str, data: dict | str | None = None) -> None:
    if data:
        print(f"\n=== {title} ===")
        if isinstance(data, dict):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(data)
    else:
        print(f"\n--- {title} ---")


async def wait_healthy() -> None:
    """Poll until the cluster is healthy."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(30):
            try:
                resp = await client.get(f"{BASE_URL}/health")
                if resp.status_code == 200:
                    log("Cluster healthy", resp.json())
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(2)
    raise RuntimeError("Cluster not healthy after 60s")


async def create_thread(client: httpx.AsyncClient) -> str:
    resp = await client.post(f"{BASE_URL}/threads", json={})
    resp.raise_for_status()
    return resp.json()["thread_id"]


async def create_run(client: httpx.AsyncClient, thread_id: str, prompt: str) -> dict:
    resp = await client.post(
        f"{BASE_URL}/threads/{thread_id}/runs",
        json={
            "assistant_id": ASSISTANT_ID,
            "input": {"messages": [{"role": "user", "content": prompt}]},
        },
    )
    resp.raise_for_status()
    return resp.json()


async def get_run(client: httpx.AsyncClient, thread_id: str, run_id: str) -> dict:
    resp = await client.get(f"{BASE_URL}/threads/{thread_id}/runs/{run_id}")
    resp.raise_for_status()
    return resp.json()


async def join_run(client: httpx.AsyncClient, thread_id: str, run_id: str) -> dict:
    resp = await client.get(
        f"{BASE_URL}/threads/{thread_id}/runs/{run_id}/join",
        timeout=httpx.Timeout(120.0),
    )
    resp.raise_for_status()
    return resp.json()


async def cancel_run(client: httpx.AsyncClient, thread_id: str, run_id: str) -> dict:
    resp = await client.post(
        f"{BASE_URL}/threads/{thread_id}/runs/{run_id}/cancel?action=cancel",
    )
    resp.raise_for_status()
    return resp.json()


async def poll_until_terminal(client: httpx.AsyncClient, thread_id: str, run_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = await get_run(client, thread_id, run_id)
        if run["status"] in ("success", "error", "interrupted"):
            return run
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Run {run_id} did not reach terminal state in {timeout}s")


# ------------------------------------------------------------------
# Test cases
# ------------------------------------------------------------------


async def test_cross_instance_create_and_join() -> None:
    """Create run on one request, join on another (nginx routes to different instances)."""
    log("TEST: Cross-instance create and join")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        thread_id = await create_thread(client)
        run = await create_run(client, thread_id, "Say 'cross-join-ok' and nothing else.")
        log("Run created", run)

        # Join via a SEPARATE connection (likely hits different instance)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client2:
            output = await join_run(client2, thread_id, run["run_id"])
            log("Join output", output)
            assert output, "Expected non-empty output"

    log("PASSED")


async def test_cross_instance_cancel() -> None:
    """Create run on one instance, cancel from another."""
    log("TEST: Cross-instance cancel")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        thread_id = await create_thread(client)
        run = await create_run(client, thread_id, "Write a very long essay about everything.")
        log("Run created", run)
        await asyncio.sleep(1)

        # Cancel via separate connection
        async with httpx.AsyncClient(timeout=TIMEOUT) as client2:
            cancelled = await cancel_run(client2, thread_id, run["run_id"])
            log("Cancel response", cancelled)

        final = await poll_until_terminal(client, thread_id, run["run_id"])
        log("Final state", final)
        assert final["status"] == "interrupted", f"Expected interrupted, got {final['status']}"

    log("PASSED")


async def test_concurrent_runs_across_instances() -> None:
    """Submit 6 runs — should distribute across 4 workers (2 per instance)."""
    log("TEST: Concurrent runs across instances")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        runs = []
        for i in range(6):
            thread_id = await create_thread(client)
            run = await create_run(client, thread_id, f"Say 'parallel-{i}' and nothing else.")
            runs.append((thread_id, run["run_id"]))
            log(f"Run {i} created", {"run_id": run["run_id"]})

        results = await asyncio.gather(*[poll_until_terminal(client, tid, rid) for tid, rid in runs])

        for i, result in enumerate(results):
            log(f"Run {i} result", {"status": result["status"]})
            assert result["status"] == "success", f"Run {i} failed: {result.get('error_message')}"

    log("PASSED")


async def test_worker_crash_recovery() -> None:
    """Kill a worker container mid-run, verify reaper recovers the run.

    Uses short lease (10s) and reaper interval (5s) configured in compose.
    """
    log("TEST: Worker crash recovery")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        thread_id = await create_thread(client)
        run = await create_run(
            client,
            thread_id,
            "Write a detailed 500-word essay about distributed systems. Take your time.",
        )
        run_id = run["run_id"]
        log("Run created", {"run_id": run_id})

        # Wait for the run to be picked up by a worker
        await asyncio.sleep(2)
        run_state = await get_run(client, thread_id, run_id)
        log("Run state before kill", run_state)

        if run_state["status"] != "running":
            log("SKIPPED (run completed before we could kill worker)")
            return

        # Kill instance B (one of the workers)
        log("Killing aegra-b container...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "kill", "aegra-b"],
            capture_output=True,
            cwd=COMPOSE_DIR,
            check=True,
        )

        # Wait for lease to expire (10s) + reaper interval (5s) + execution time
        log("Waiting for lease expiry + reaper recovery (up to 30s)...")
        try:
            final = await poll_until_terminal(client, thread_id, run_id, timeout=60.0)
            log("Final state after recovery", final)
            # The run should either succeed (re-executed by instance A's worker)
            # or be in error state (if the graph couldn't resume from checkpoint)
            assert final["status"] in ("success", "error", "interrupted"), f"Unexpected status: {final['status']}"
            if final["status"] == "success":
                log("Run recovered and completed successfully!")
            else:
                log(f"Run recovered but ended in {final['status']} (expected for non-checkpointed graphs)")
        finally:
            # Restart instance B
            log("Restarting aegra-b...")
            subprocess.run(
                ["docker", "compose", "-f", "docker-compose.multi.yml", "up", "-d", "aegra-b"],
                capture_output=True,
                cwd=COMPOSE_DIR,
                check=True,
            )
            await asyncio.sleep(5)

    log("PASSED")


async def test_sse_stream_cross_instance() -> None:
    """Stream a run — events should arrive even if load balancer routes to non-executing instance."""
    log("TEST: SSE stream cross-instance")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        thread_id = await create_thread(client)

        # Create and stream via POST
        async with client.stream(
            "POST",
            f"{BASE_URL}/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": ASSISTANT_ID,
                "input": {"messages": [{"role": "user", "content": "Say 'stream-cross-ok' and nothing else."}]},
            },
            timeout=httpx.Timeout(60.0),
        ) as response:
            events = []
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    events.append(event_type)
                    if event_type == "end":
                        break

            log("Stream events received", {"events": events, "count": len(events)})
            assert len(events) > 0, "Expected at least one SSE event"
            assert "metadata" in events, "Expected metadata event"

    log("PASSED")


async def test_wait_endpoint_cross_instance() -> None:
    """/runs/wait should return output even when worker is on a different instance."""
    log("TEST: Wait endpoint cross-instance")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        thread_id = await create_thread(client)

        resp = await client.post(
            f"{BASE_URL}/threads/{thread_id}/runs/wait",
            json={
                "assistant_id": ASSISTANT_ID,
                "input": {"messages": [{"role": "user", "content": "Say 'wait-cross-ok' and nothing else."}]},
            },
            timeout=httpx.Timeout(120.0),
        )
        resp.raise_for_status()
        output = resp.json()
        log("Wait output", output)
        assert output, "Expected non-empty output"

    log("PASSED")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------


async def main() -> None:
    print("=" * 60)
    print("Multi-Instance E2E Tests")
    print("=" * 60)

    await wait_healthy()

    tests = [
        test_cross_instance_create_and_join,
        test_cross_instance_cancel,
        test_concurrent_runs_across_instances,
        test_sse_stream_cross_instance,
        test_wait_endpoint_cross_instance,
        test_worker_crash_recovery,  # Last because it kills a container
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as exc:
            log(f"FAILED: {test.__name__}", str(exc))
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
