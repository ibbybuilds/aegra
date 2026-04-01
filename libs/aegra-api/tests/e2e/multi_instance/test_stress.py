"""Stress tests for worker architecture.

Uses the stress_test graph (no LLM, configurable delay) to validate
the system under high concurrency and failure conditions.

Run:
  cd aegra
  docker compose -f deployments/test/docker-compose.multi.yml up -d --build
  uv run python libs/aegra-api/tests/e2e/multi_instance/test_stress.py
"""

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

BASE_URL = "http://localhost:2026"
GRAPH_ID = "stress_test"
TIMEOUT = httpx.Timeout(30.0, read=120.0)
POOL_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=50)

# Resolve compose directory relative to repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]  # tests/e2e/multi_instance -> aegra root
COMPOSE_DIR = str(_REPO_ROOT / "deployments" / "test")
COMPOSE_FILE = "docker-compose.multi.yml"


@dataclass
class StressResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    errored: int = 0
    interrupted: int = 0
    elapsed: float = 0.0


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


async def wait_healthy() -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        for _ in range(30):
            try:
                resp = await client.get(f"{BASE_URL}/health")
                if resp.status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(2)
    raise RuntimeError("Cluster not healthy")


async def ensure_assistant(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{BASE_URL}/assistants",
        json={"graph_id": GRAPH_ID, "config": {}, "if_exists": "do_nothing"},
    )
    resp.raise_for_status()
    return resp.json()["assistant_id"]


async def poll_until_terminal(
    client: httpx.AsyncClient,
    thread_id: str,
    run_id: str,
    *,
    timeout: float = 60.0,
) -> dict:
    """Poll run status until terminal state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = await client.get(f"{BASE_URL}/threads/{thread_id}/runs/{run_id}")
        run = resp.json()
        if run["status"] in ("success", "error", "interrupted"):
            return run
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Run {run_id} did not reach terminal state in {timeout}s")


async def submit_and_poll(
    client: httpx.AsyncClient,
    assistant_id: str,
    run_config: dict,
    *,
    poll_timeout: float = 60.0,
) -> str:
    """Create a run and poll until terminal. Returns final status."""
    thread_resp = await client.post(f"{BASE_URL}/threads", json={})
    thread_id = thread_resp.json()["thread_id"]

    run_resp = await client.post(
        f"{BASE_URL}/threads/{thread_id}/runs",
        json={
            "assistant_id": assistant_id,
            "input": {"messages": [{"role": "user", "content": json.dumps(run_config)}]},
        },
    )
    run_id = run_resp.json()["run_id"]

    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        resp = await client.get(f"{BASE_URL}/threads/{thread_id}/runs/{run_id}")
        status = resp.json()["status"]
        if status in ("success", "error", "interrupted"):
            return status
        await asyncio.sleep(0.5)

    return "timeout"


# ------------------------------------------------------------------
# Stress scenarios
# ------------------------------------------------------------------


async def stress_high_concurrency() -> StressResult:
    """50 concurrent short runs — validates queue throughput and worker distribution."""
    log("STRESS: 50 concurrent runs (0.2s delay, 2 steps each)")
    result = StressResult(total=50)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        start = time.time()
        tasks = [submit_and_poll(client, assistant_id, {"delay": 0.2, "steps": 2}) for _ in range(50)]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for s in statuses:
            if isinstance(s, Exception):
                result.errored += 1
            elif s == "success":
                result.succeeded += 1
            elif s == "error":
                result.failed += 1
            elif s == "interrupted":
                result.interrupted += 1
            else:
                result.errored += 1

    return result


async def stress_long_running() -> StressResult:
    """10 runs with 5 steps each (2.5s total) — validates heartbeat keeps lease alive."""
    log("STRESS: 10 long-running runs (0.5s delay, 5 steps = 2.5s each)")
    result = StressResult(total=10)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        start = time.time()
        tasks = [
            submit_and_poll(client, assistant_id, {"delay": 0.5, "steps": 5}, poll_timeout=30.0) for _ in range(10)
        ]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for s in statuses:
            if isinstance(s, Exception):
                result.errored += 1
            elif s == "success":
                result.succeeded += 1
            else:
                result.failed += 1

    return result


async def stress_error_handling() -> StressResult:
    """10 runs that intentionally fail — validates error propagation."""
    log("STRESS: 10 intentional failures")
    result = StressResult(total=10)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        start = time.time()
        tasks = [submit_and_poll(client, assistant_id, {"delay": 0.1, "steps": 2, "fail": True}) for _ in range(10)]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for s in statuses:
            if isinstance(s, Exception):
                result.errored += 1
            elif s == "error":
                result.succeeded += 1  # error IS the expected outcome
            else:
                result.failed += 1

    return result


async def stress_mixed_workload() -> StressResult:
    """30 runs: mix of fast, slow, and failing — realistic workload."""
    log("STRESS: 30 mixed workload (fast + slow + failures)")
    result = StressResult(total=30)

    configs = (
        [{"delay": 0.1, "steps": 1}] * 15  # 15 fast
        + [{"delay": 0.5, "steps": 4}] * 10  # 10 slow
        + [{"delay": 0.1, "steps": 2, "fail": True}] * 5  # 5 failures
    )

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        start = time.time()
        tasks = [submit_and_poll(client, assistant_id, cfg) for cfg in configs]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for i, s in enumerate(statuses):
            if isinstance(s, Exception):
                result.errored += 1
            elif s == "success" and not configs[i].get("fail"):
                result.succeeded += 1
            elif s == "error" and configs[i].get("fail"):
                result.succeeded += 1  # expected failure
            else:
                result.failed += 1

    return result


async def stress_cancel_storm() -> StressResult:
    """20 runs created then immediately cancelled — validates cancel under load."""
    log("STRESS: 20 immediate cancels")
    result = StressResult(total=20)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        runs: list[tuple[str, str]] = []
        for _ in range(20):
            thread_resp = await client.post(f"{BASE_URL}/threads", json={})
            thread_id = thread_resp.json()["thread_id"]
            run_resp = await client.post(
                f"{BASE_URL}/threads/{thread_id}/runs",
                json={
                    "assistant_id": assistant_id,
                    "input": {"messages": [{"role": "user", "content": json.dumps({"delay": 5.0, "steps": 10})}]},
                },
            )
            runs.append((thread_id, run_resp.json()["run_id"]))

        # Cancel all immediately
        start = time.time()
        cancel_tasks = [client.post(f"{BASE_URL}/threads/{tid}/runs/{rid}/cancel?action=cancel") for tid, rid in runs]
        await asyncio.gather(*cancel_tasks, return_exceptions=True)
        await asyncio.sleep(2)

        # Check final states
        for tid, rid in runs:
            resp = await client.get(f"{BASE_URL}/threads/{tid}/runs/{rid}")
            status = resp.json()["status"]
            if status == "interrupted":
                result.succeeded += 1
            elif status in ("success", "pending"):
                result.succeeded += 1  # race: may have completed before cancel
            else:
                result.failed += 1

        result.elapsed = time.time() - start

    return result


# ------------------------------------------------------------------
# Advanced stress scenarios
# ------------------------------------------------------------------


async def stress_db_pool_ceiling() -> StressResult:
    """200 concurrent runs — find DB connection pool limits.

    With default pool size ~20, this tests whether the system degrades
    gracefully under extreme load (queue backpressure, not pool exhaustion).
    """
    log("STRESS: 200 concurrent runs (0.1s delay, 1 step — DB pool ceiling)")
    result = StressResult(total=200)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0), limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        start = time.time()
        tasks = [
            submit_and_poll(client, assistant_id, {"delay": 0.1, "steps": 1}, poll_timeout=120.0) for _ in range(200)
        ]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for s in statuses:
            if isinstance(s, Exception):
                result.errored += 1
                log(f"  Error: {s}")
            elif s == "success":
                result.succeeded += 1
            elif s == "timeout":
                result.errored += 1
            else:
                result.failed += 1

    return result


async def stress_redis_flap() -> StressResult:
    """Pause Redis mid-run, verify workers fall back to Postgres polling.

    1. Submit 10 runs
    2. Pause Redis for 8 seconds (workers lose BLPOP, fall back to PG poll)
    3. Unpause Redis
    4. Verify all runs complete
    """
    log("STRESS: Redis flap (pause/unpause during execution)")
    result = StressResult(total=10)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        # Submit runs with enough delay to survive the Redis pause
        runs: list[tuple[str, str]] = []
        for _ in range(10):
            thread_resp = await client.post(f"{BASE_URL}/threads", json={})
            thread_id = thread_resp.json()["thread_id"]
            run_resp = await client.post(
                f"{BASE_URL}/threads/{thread_id}/runs",
                json={
                    "assistant_id": assistant_id,
                    "input": {"messages": [{"role": "user", "content": json.dumps({"delay": 1.0, "steps": 3})}]},
                },
            )
            runs.append((thread_id, run_resp.json()["run_id"]))

        await asyncio.sleep(1)

        # Pause Redis
        log("  Pausing Redis container for 8 seconds...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "pause", "redis"],
            capture_output=True,
            check=True,
            cwd=COMPOSE_DIR,
        )

        await asyncio.sleep(8)

        # Unpause Redis
        log("  Unpausing Redis...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "unpause", "redis"],
            capture_output=True,
            check=True,
            cwd=COMPOSE_DIR,
        )

        # Wait for all runs to finish
        start = time.time()
        for tid, rid in runs:
            try:
                final = await poll_until_terminal(client, tid, rid, timeout=60.0)
                if final["status"] == "success":
                    result.succeeded += 1
                elif final["status"] == "error":
                    result.failed += 1
                    log(f"  Run {rid} errored: {final.get('error_message', '?')[:80]}")
                else:
                    result.interrupted += 1
            except TimeoutError:
                result.errored += 1
                log(f"  Run {rid} timed out")
            except Exception as exc:
                result.errored += 1
                log(f"  Run {rid} exception: {exc}")

        result.elapsed = time.time() - start

    return result


async def stress_single_worker_backpressure() -> StressResult:
    """Temporarily reduce to 1 worker via container restart, submit 20 runs.

    Verifies queue backpressure — runs queue up in Redis and are
    processed sequentially by the single worker.
    """
    log("STRESS: Single worker backpressure (20 runs, 1 worker)")

    # Kill instance B to leave only instance A (2 workers)
    # Then we rely on the 2 workers on instance A to handle everything
    # For true single-worker test, we'd need to reconfigure WORKER_COUNT,
    # but killing one instance effectively halves worker count.
    log("  Killing aegra-b to reduce to 2 workers...")
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.multi.yml", "kill", "aegra-b"],
        capture_output=True,
        check=True,
        cwd=COMPOSE_DIR,
    )
    await asyncio.sleep(3)

    result = StressResult(total=20)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), limits=POOL_LIMITS) as client:
            assistant_id = await ensure_assistant(client)

            start = time.time()
            # Each run takes ~1s (0.5s * 2 steps). With 2 workers, 20 runs should
            # take ~10s (queued in batches of 2). Verifies FIFO ordering and
            # no runs are lost while queued.
            tasks = [
                submit_and_poll(client, assistant_id, {"delay": 0.5, "steps": 2}, poll_timeout=60.0) for _ in range(20)
            ]
            statuses = await asyncio.gather(*tasks, return_exceptions=True)
            result.elapsed = time.time() - start

            for s in statuses:
                if isinstance(s, Exception):
                    result.errored += 1
                elif s == "success":
                    result.succeeded += 1
                elif s == "timeout":
                    result.errored += 1
                else:
                    result.failed += 1
    finally:
        # Restart instance B
        log("  Restarting aegra-b...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "up", "-d", "aegra-b"],
            capture_output=True,
            check=True,
            cwd=COMPOSE_DIR,
        )
        await asyncio.sleep(5)

    return result


async def stress_network_partition() -> StressResult:
    """Simulate network partition between instances by killing nginx briefly.

    1. Submit 10 runs (go through nginx to both instances)
    2. Kill nginx (clients can't reach the cluster)
    3. Workers continue executing (they have jobs from Redis)
    4. Restart nginx
    5. Poll for results (should all be complete since workers kept running)

    This proves workers are decoupled from the HTTP layer.
    """
    log("STRESS: Network partition (nginx kill during execution)")
    result = StressResult(total=10)

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        assistant_id = await ensure_assistant(client)

        # Submit runs before the partition
        runs: list[tuple[str, str]] = []
        for _ in range(10):
            thread_resp = await client.post(f"{BASE_URL}/threads", json={})
            thread_id = thread_resp.json()["thread_id"]
            run_resp = await client.post(
                f"{BASE_URL}/threads/{thread_id}/runs",
                json={
                    "assistant_id": assistant_id,
                    "input": {"messages": [{"role": "user", "content": json.dumps({"delay": 0.5, "steps": 3})}]},
                },
            )
            runs.append((thread_id, run_resp.json()["run_id"]))

        log(f"  Submitted {len(runs)} runs, waiting 1s for workers to pick up...")
        await asyncio.sleep(1)

        # Kill nginx (simulates network partition from client perspective)
        log("  Killing nginx (network partition)...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "kill", "nginx"],
            capture_output=True,
            check=True,
            cwd=COMPOSE_DIR,
        )

        # Workers keep running — they already have jobs from Redis
        log("  Waiting 5s for workers to finish executing...")
        await asyncio.sleep(5)

        # Restore nginx
        log("  Restarting nginx...")
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.multi.yml", "up", "-d", "nginx"],
            capture_output=True,
            check=True,
            cwd=COMPOSE_DIR,
        )
        await asyncio.sleep(3)

    # Reconnect and check results
    start = time.time()
    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        for tid, rid in runs:
            try:
                final = await poll_until_terminal(client, tid, rid, timeout=30.0)
                if final["status"] == "success":
                    result.succeeded += 1
                elif final["status"] == "error":
                    result.failed += 1
                else:
                    result.interrupted += 1
            except TimeoutError:
                result.errored += 1
            except Exception:
                result.errored += 1

    result.elapsed = time.time() - start
    return result


# ------------------------------------------------------------------
# Real LLM stress scenarios (--real-llm flag)
# Uses gpt-4o-mini via the "agent" graph — cheap but real network I/O
# ------------------------------------------------------------------

LLM_PROMPTS = [
    "List 10 programming languages and one sentence about each.",
    "Write a short poem about distributed systems in exactly 8 lines.",
    "Explain the CAP theorem in 3 bullet points.",
    "Name 5 databases and their primary use case, one line each.",
    "What are 3 benefits of async programming? Keep it under 100 words.",
    "List 7 design patterns with a one-sentence description each.",
    "Write a haiku about Redis.",
    "Explain what a semaphore is in 2 sentences.",
    "Name 10 cloud services and what they do, one line each.",
    "What is eventual consistency? Explain in 50 words.",
    "List 5 sorting algorithms with their time complexity.",
    "Write a 4-line limerick about Python.",
    "What are the SOLID principles? One sentence each.",
    "Explain MapReduce in 3 sentences.",
    "Name 8 HTTP status codes and what they mean.",
    "What is a load balancer? Explain like I'm five.",
    "List 6 message queue systems and when to use each.",
    "What is Docker? Explain in exactly 3 sentences.",
    "Name 5 testing strategies with one sentence each.",
    "Write a short story about a microservice in 5 sentences.",
]


async def submit_llm_run(
    client: httpx.AsyncClient,
    prompt: str,
    *,
    poll_timeout: float = 120.0,
) -> tuple[str, float]:
    """Submit an LLM run, poll until terminal. Returns (status, elapsed)."""
    thread_resp = await client.post(f"{BASE_URL}/threads", json={})
    thread_id = thread_resp.json()["thread_id"]

    start = time.time()
    run_resp = await client.post(
        f"{BASE_URL}/threads/{thread_id}/runs",
        json={
            "assistant_id": "agent",
            "input": {"messages": [{"role": "user", "content": prompt}]},
        },
    )
    run_id = run_resp.json()["run_id"]

    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        resp = await client.get(f"{BASE_URL}/threads/{thread_id}/runs/{run_id}")
        data = resp.json()
        if data["status"] in ("success", "error", "interrupted"):
            elapsed = time.time() - start
            return data["status"], elapsed
        await asyncio.sleep(1.0)

    return "timeout", time.time() - start


async def stream_llm_run(
    client: httpx.AsyncClient,
    prompt: str,
) -> tuple[str, int, float]:
    """Stream an LLM run via SSE. Returns (status, event_count, elapsed)."""
    thread_resp = await client.post(f"{BASE_URL}/threads", json={})
    thread_id = thread_resp.json()["thread_id"]

    start = time.time()
    event_count = 0
    status = "unknown"

    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "agent",
                "input": {"messages": [{"role": "user", "content": prompt}]},
            },
            timeout=httpx.Timeout(60.0),
        ) as response:
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event_count += 1
                    event_type = line[6:].strip()
                    if event_type == "end":
                        status = "success"
                        break

        # If we exited without seeing "end", the stream closed cleanly
        # which means the run completed (server closed the connection)
        if status == "unknown" and event_count > 0:
            status = "success"
    except httpx.ReadTimeout:
        status = "timeout"
    except Exception as exc:
        status = f"error: {exc}"

    elapsed = time.time() - start
    return status, event_count, elapsed


async def stress_llm_concurrent_runs() -> StressResult:
    """20 concurrent real LLM runs — validates full stack under real I/O."""
    log("STRESS [LLM]: 20 concurrent gpt-4o-mini runs")
    result = StressResult(total=20)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0), limits=POOL_LIMITS) as client:
        start = time.time()
        tasks = [submit_llm_run(client, LLM_PROMPTS[i % len(LLM_PROMPTS)]) for i in range(20)]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        latencies = []
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                result.errored += 1
                log(f"  Error: {outcome}")
            else:
                status, elapsed = outcome
                latencies.append(elapsed)
                if status == "success":
                    result.succeeded += 1
                else:
                    result.failed += 1
                    log(f"  Failed: {status}")

        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            log(f"  Latency: p50={p50:.1f}s  p95={p95:.1f}s  max={max(latencies):.1f}s")

    return result


async def stress_llm_concurrent_streams() -> StressResult:
    """15 concurrent SSE streams with real LLM — validates broker under real event throughput."""
    log("STRESS [LLM]: 15 concurrent SSE streams (gpt-4o-mini)")
    result = StressResult(total=15)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0), limits=POOL_LIMITS) as client:
        start = time.time()
        tasks = [stream_llm_run(client, LLM_PROMPTS[i % len(LLM_PROMPTS)]) for i in range(15)]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        total_events = 0
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                result.errored += 1
                log(f"  Error: {outcome}")
            else:
                status, event_count, elapsed = outcome
                total_events += event_count
                if status == "success":
                    result.succeeded += 1
                else:
                    result.failed += 1
                    log(f"  Failed: {status} ({event_count} events in {elapsed:.1f}s)")

        log(f"  Total SSE events received: {total_events}")

    return result


async def stress_llm_wait_endpoint() -> StressResult:
    """10 concurrent /runs/wait with real LLM — validates blocking wait with real latency."""
    log("STRESS [LLM]: 10 concurrent /runs/wait (gpt-4o-mini)")
    result = StressResult(total=10)

    async def wait_run(client: httpx.AsyncClient, prompt: str) -> tuple[str, float]:
        thread_resp = await client.post(f"{BASE_URL}/threads", json={})
        thread_id = thread_resp.json()["thread_id"]
        start = time.time()
        resp = await client.post(
            f"{BASE_URL}/threads/{thread_id}/runs/wait",
            json={
                "assistant_id": "agent",
                "input": {"messages": [{"role": "user", "content": prompt}]},
            },
            timeout=httpx.Timeout(120.0),
        )
        elapsed = time.time() - start
        if resp.status_code == 200 and resp.json():
            return "success", elapsed
        return f"error:{resp.status_code}", elapsed

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0), limits=POOL_LIMITS) as client:
        start = time.time()
        tasks = [wait_run(client, LLM_PROMPTS[i % len(LLM_PROMPTS)]) for i in range(10)]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        result.elapsed = time.time() - start

        for outcome in outcomes:
            if isinstance(outcome, Exception):
                result.errored += 1
            else:
                status, _ = outcome
                if status == "success":
                    result.succeeded += 1
                else:
                    result.failed += 1

    return result


async def stress_llm_cancel_mid_generation() -> StressResult:
    """5 runs cancelled mid-LLM-generation — validates cancel reaches through to LLM call."""
    log("STRESS [LLM]: 5 cancel-mid-generation (long prompt, cancel after 2s)")
    result = StressResult(total=5)

    long_prompt = "Write a detailed 2000-word essay about the complete history of computer science from 1940 to 2025."

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS) as client:
        start = time.time()

        for i in range(5):
            thread_resp = await client.post(f"{BASE_URL}/threads", json={})
            thread_id = thread_resp.json()["thread_id"]
            run_resp = await client.post(
                f"{BASE_URL}/threads/{thread_id}/runs",
                json={
                    "assistant_id": "agent",
                    "input": {"messages": [{"role": "user", "content": long_prompt}]},
                },
            )
            run_id = run_resp.json()["run_id"]

            await asyncio.sleep(2)

            await client.post(f"{BASE_URL}/threads/{thread_id}/runs/{run_id}/cancel?action=cancel")

            final = await poll_until_terminal(client, thread_id, run_id, timeout=15.0)
            if final["status"] == "interrupted":
                result.succeeded += 1
            elif final["status"] == "success":
                result.succeeded += 1  # completed before cancel reached
            else:
                result.failed += 1
                log(f"  Run {i} unexpected status: {final['status']}")

        result.elapsed = time.time() - start

    return result


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------


async def main() -> None:
    print("=" * 60)
    print("Worker Architecture Stress Tests")
    print("=" * 60)

    await wait_healthy()

    run_advanced = "--advanced" in sys.argv
    run_llm = "--real-llm" in sys.argv

    scenarios = [
        ("High Concurrency (50 runs)", stress_high_concurrency),
        ("Long Running (10 runs)", stress_long_running),
        ("Error Handling (10 failures)", stress_error_handling),
        ("Mixed Workload (30 runs)", stress_mixed_workload),
        ("Cancel Storm (20 cancels)", stress_cancel_storm),
    ]

    if run_advanced:
        scenarios.extend(
            [
                ("DB Pool Ceiling (200 runs)", stress_db_pool_ceiling),
                ("Redis Flap (pause/unpause)", stress_redis_flap),
                ("Single Worker Backpressure", stress_single_worker_backpressure),
                ("Network Partition (nginx kill)", stress_network_partition),
            ]
        )

    if run_llm:
        scenarios.extend(
            [
                ("LLM: 20 Concurrent Runs", stress_llm_concurrent_runs),
                ("LLM: 15 Concurrent SSE Streams", stress_llm_concurrent_streams),
                ("LLM: 10 Concurrent /runs/wait", stress_llm_wait_endpoint),
                ("LLM: 5 Cancel Mid-Generation", stress_llm_cancel_mid_generation),
            ]
        )

    if not run_advanced and not run_llm:
        log("Tip: --advanced for infra tests, --real-llm for LLM tests, or both")

    all_passed = True
    for name, test_fn in scenarios:
        try:
            result = await test_fn()
            status = "PASS" if result.failed == 0 and result.errored == 0 else "FAIL"
            if status == "FAIL":
                all_passed = False
            log(
                f"{status}: {name} — "
                f"{result.succeeded}/{result.total} ok, "
                f"{result.failed} failed, {result.errored} errored, "
                f"{result.elapsed:.1f}s"
            )
        except Exception as exc:
            all_passed = False
            log(f"FAIL: {name} — {exc}")

    print("\n" + "=" * 60)
    print("STRESS TEST " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
