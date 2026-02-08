"""LangGraph SDK streaming latency probe.

This script helps reproduce slow streaming behaviour when the server is backed
by a remote Postgres instance.  It uses the official ``langgraph-sdk`` to send
HTTP requests and records timing information for each streamed chunk.

Usage examples::

    uv run python test_sdk_integration.py --prompt "ping" --iterations 3
    uv run python test_sdk_integration.py --api-url http://localhost:8000 \
        --graph-id agent --stream-mode messages-tuple --print-chunks

Environment variables can be used instead of CLI arguments:

``AEGRA_API_URL``      – Server base URL (default ``http://localhost:8000``)
``AEGRA_API_KEY``      – Optional API key if auth is enabled
``AEGRA_GRAPH_ID``     – Graph identifier (default ``agent``)
``AEGRA_ASSISTANT_ID`` – Explicit assistant ID override
``AEGRA_STREAM_MODE``  – Stream mode passed to the server
``AEGRA_PROMPT``       – Prompt content
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid5

# Add libs/aegra-api/src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "libs" / "aegra-api" / "src"))

from langgraph_sdk import get_client

from aegra_api.constants import ASSISTANT_NAMESPACE_UUID

DEFAULT_API_URL = os.getenv("AEGRA_API_URL", "http://localhost:8000")
DEFAULT_PROMPT = os.getenv("AEGRA_PROMPT", "Hello from LangGraph SDK!")
DEFAULT_GRAPH_ID = os.getenv("AEGRA_GRAPH_ID", "agent")
DEFAULT_STREAM_MODE = os.getenv("AEGRA_STREAM_MODE", "messages-tuple")
DEFAULT_ITERATIONS = 1


@dataclass
class ChunkRecord:
    idx: int
    event: str
    elapsed: float
    payload: Any


async def stream_once(
    *,
    api_url: str,
    api_key: str | None,
    assistant_id: str,
    graph_id: str,
    prompt: str,
    stream_mode: str,
    print_chunks: bool,
    threadless: bool,
) -> dict[str, Any]:
    """Run a single streaming request and collect timing metrics."""

    client = get_client(url=api_url, api_key=api_key)

    if threadless:
        thread_id = None
    else:
        thread = await client.threads.create()
        thread_id = thread["thread_id"]

    request_payload = {
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ]
    }

    chunk_records: list[ChunkRecord] = []
    start_time = time.perf_counter()
    first_chunk_time: float | None = None

    async for chunk in client.runs.stream(
        thread_id,
        assistant_id,
        input=request_payload,
        stream_mode=stream_mode,
    ):
        now = time.perf_counter()
        if first_chunk_time is None:
            first_chunk_time = now
        elapsed = now - start_time
        record = ChunkRecord(
            idx=len(chunk_records),
            event=chunk.event,
            elapsed=elapsed,
            payload=chunk.data,
        )
        chunk_records.append(record)
        if print_chunks:
            pretty_payload = json.dumps(chunk.data, indent=2, default=str)
            print(f"[{record.idx}] +{elapsed:.3f}s {chunk.event}:\n{pretty_payload}\n")

    end_time = time.perf_counter()

    deltas: list[float] = []
    for prev, current in zip(chunk_records, chunk_records[1:], strict=False):
        deltas.append(current.elapsed - prev.elapsed)

    return {
        "thread_id": thread_id,
        "graph_id": graph_id,
        "assistant_id": assistant_id,
        "prompt": prompt,
        "stream_mode": stream_mode,
        "chunks": chunk_records,
        "chunk_count": len(chunk_records),
        "total_duration": end_time - start_time,
        "first_chunk_latency": None
        if first_chunk_time is None
        else first_chunk_time - start_time,
        "inter_chunk_deltas": deltas,
    }


def summarise_run(run_result: dict[str, Any]) -> str:
    """Format a concise summary for a streaming run."""

    chunk_count = run_result["chunk_count"]
    total_duration = run_result["total_duration"]
    first_latency = run_result["first_chunk_latency"]
    deltas = run_result["inter_chunk_deltas"]

    stats_parts: list[str] = [f"chunks={chunk_count}", f"total={total_duration:.3f}s"]
    if first_latency is not None:
        stats_parts.append(f"first={first_latency:.3f}s")
    if deltas:
        stats_parts.append(f"mean_delta={statistics.mean(deltas):.3f}s")
        stats_parts.append(f"p95_delta={percentile(deltas, 95):.3f}s")
    return ", ".join(stats_parts)


def percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return float("nan")
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(sorted_vals) - 1)
    if lower == upper:
        return sorted_vals[lower]
    weight = k - lower
    return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Aegra server URL")
    parser.add_argument(
        "--api-key", default=os.getenv("AEGRA_API_KEY"), help="Optional API key"
    )
    parser.add_argument(
        "--graph-id", default=DEFAULT_GRAPH_ID, help="Graph identifier to target"
    )
    parser.add_argument(
        "--assistant-id",
        default=os.getenv("AEGRA_ASSISTANT_ID"),
        help="Assistant ID override",
    )
    parser.add_argument(
        "--prompt", default=DEFAULT_PROMPT, help="Prompt content to send"
    )
    parser.add_argument(
        "--stream-mode",
        default=DEFAULT_STREAM_MODE,
        help="Stream mode (messages, messages-tuple, updates, ...)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Number of runs to execute",
    )
    parser.add_argument(
        "--threadless",
        action="store_true",
        help="Use threadless runs (pass None as thread_id)",
    )
    parser.add_argument(
        "--print-chunks",
        action="store_true",
        help="Print each chunk payload for troubleshooting",
    )
    return parser.parse_args(list(argv))


async def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    assistant_id = args.assistant_id or str(
        uuid5(ASSISTANT_NAMESPACE_UUID, args.graph_id)
    )

    print(
        "Streaming benchmark starting...",
        f"url={args.api_url}",
        f"graph={args.graph_id}",
        f"assistant={assistant_id}",
        f"stream_mode={args.stream_mode}",
    )

    results: list[dict[str, Any]] = []
    for idx in range(args.iterations):
        print(f"\nIteration {idx + 1}/{args.iterations}...")
        result = await stream_once(
            api_url=args.api_url,
            api_key=args.api_key,
            assistant_id=assistant_id,
            graph_id=args.graph_id,
            prompt=args.prompt,
            stream_mode=args.stream_mode,
            print_chunks=args.print_chunks,
            threadless=args.threadless,
        )
        print("Summary:", summarise_run(result))
        results.append(result)

    if args.iterations > 1:
        totals = [item["total_duration"] for item in results]
        firsts = [
            item["first_chunk_latency"]
            for item in results
            if item["first_chunk_latency"] is not None
        ]
        print("\nBatch summary:")
        print(
            f"  total mean={statistics.mean(totals):.3f}s p95={percentile(totals, 95):.3f}s"
        )
        if firsts:
            print(
                f"  first-chunk mean={statistics.mean(firsts):.3f}s p95={percentile(firsts, 95):.3f}s"
            )

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:  # pragma: no cover - manual interrupt
        exit_code = 130
    sys.exit(exit_code)
