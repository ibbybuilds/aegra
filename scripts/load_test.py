"""
Load testing script for Aegra server capacity validation.

Tests the server's ability to handle:
- 300 concurrent HTTP connections
- 90 concurrent SSE streaming responses
- 15-minute request timeouts
- 200+ sustained concurrent calls

Usage:
    export AEGRA_URL="http://localhost:8000"
    export AEGRA_TOKEN="<jwt-token>"  # Generate with scripts/generate_jwt_token.py
    python scripts/load_test.py

Requirements:
    - httpx
    - asyncio
    - Server must be running (docker compose up or uvicorn)
    - Valid JWT token if AUTH_TYPE=custom
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: uv pip install httpx")
    sys.exit(1)


@dataclass
class TestMetrics:
    """Metrics collected during load testing."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_errors: int = 0
    connection_errors: int = 0
    pool_exhausted_errors: int = 0
    sse_connections_opened: int = 0
    sse_connections_dropped: int = 0
    response_times: List[float] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def record_success(self, response_time: float):
        """Record a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.response_times.append(response_time)

    def record_failure(self, error_type: str, error_msg: str):
        """Record a failed request."""
        self.total_requests += 1
        self.failed_requests += 1

        if "timeout" in error_msg.lower():
            self.timeout_errors += 1
        elif "connection" in error_msg.lower():
            self.connection_errors += 1
        elif "pool" in error_msg.lower() or "exhausted" in error_msg.lower():
            self.pool_exhausted_errors += 1

        self.errors.append({
            "type": error_type,
            "message": error_msg,
            "timestamp": datetime.now().isoformat()
        })

    def print_summary(self, test_name: str):
        """Print test results summary."""
        duration = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0

        print(f"\n{'='*60}")
        print(f"TEST: {test_name}")
        print(f"{'='*60}")
        print(f"Duration: {duration:.2f}s")
        print(f"Total Requests: {self.total_requests}")
        print(f"Successful: {self.successful_requests} ({success_rate:.1f}%)")
        print(f"Failed: {self.failed_requests}")
        print(f"  - Timeout errors: {self.timeout_errors}")
        print(f"  - Connection errors: {self.connection_errors}")
        print(f"  - Pool exhausted: {self.pool_exhausted_errors}")

        if self.sse_connections_opened > 0:
            print(f"\nSSE Connections:")
            print(f"  - Opened: {self.sse_connections_opened}")
            print(f"  - Dropped: {self.sse_connections_dropped}")

        if self.response_times:
            sorted_times = sorted(self.response_times)
            p50_idx = int(len(sorted_times) * 0.5)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)

            print(f"\nResponse Times:")
            print(f"  - Min: {min(sorted_times):.3f}s")
            print(f"  - Max: {max(sorted_times):.3f}s")
            print(f"  - Mean: {sum(sorted_times)/len(sorted_times):.3f}s")
            print(f"  - p50: {sorted_times[p50_idx]:.3f}s")
            print(f"  - p95: {sorted_times[p95_idx]:.3f}s")
            print(f"  - p99: {sorted_times[p99_idx]:.3f}s")

        if self.errors and self.failed_requests > 0:
            print(f"\nRecent Errors (showing last 5):")
            for error in self.errors[-5:]:
                print(f"  - [{error['type']}] {error['message']}")

        print(f"{'='*60}\n")


class LoadTester:
    """Load testing orchestrator for Aegra server."""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def health_check(self) -> bool:
        """Verify server is accessible."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                if response.status_code == 200:
                    print(f"✓ Server health check passed: {response.json()}")
                    return True
                else:
                    print(f"✗ Server health check failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"✗ Server health check failed: {e}")
            return False

    async def create_assistant(self, client: httpx.AsyncClient) -> Optional[str]:
        """Create a test assistant."""
        try:
            response = await client.post(
                f"{self.base_url}/assistants",
                json={
                    "name": "load-test-assistant",
                    "graph_id": "agent"  # Use simple agent graph for load testing
                },
                headers=self.headers,
                timeout=10.0
            )
            if response.status_code in [200, 201]:
                return response.json()["assistant_id"]
            return None
        except Exception as e:
            print(f"Warning: Failed to create assistant: {e}")
            return None

    async def create_thread(self, client: httpx.AsyncClient, assistant_id: str) -> Optional[str]:
        """Create a test thread."""
        try:
            response = await client.post(
                f"{self.base_url}/threads",
                json={"metadata": {"assistant_id": assistant_id}},
                headers=self.headers,
                timeout=10.0
            )
            if response.status_code in [200, 201]:
                return response.json()["thread_id"]
            return None
        except Exception as e:
            print(f"Warning: Failed to create thread: {e}")
            return None

    async def create_run(self, client: httpx.AsyncClient, thread_id: str, assistant_id: str) -> Optional[str]:
        """Create a run and return run_id."""
        start_time = time.time()
        try:
            response = await client.post(
                f"{self.base_url}/threads/{thread_id}/runs",
                json={
                    "assistant_id": assistant_id,
                    "input": {"messages": [{"role": "user", "content": "Hello, what hotels are available?"}]}
                },
                headers=self.headers,
                timeout=30.0
            )
            response_time = time.time() - start_time

            if response.status_code in [200, 201]:
                return response.json()["run_id"], response_time
            else:
                return None, response_time
        except Exception as e:
            response_time = time.time() - start_time
            raise

    async def stream_run(self, thread_id: str, run_id: str, duration_seconds: int, metrics: TestMetrics) -> bool:
        """Open SSE stream and keep alive for duration."""
        metrics.sse_connections_opened += 1
        start_time = time.time()
        event_count = 0

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(duration_seconds + 60.0)) as client:
                async with client.stream(
                    "GET",
                    f"{self.base_url}/threads/{thread_id}/runs/{run_id}/stream",
                    headers=self.headers
                ) as response:
                    if response.status_code != 200:
                        metrics.sse_connections_dropped += 1
                        return False

                    # Read events for specified duration
                    async for line in response.aiter_lines():
                        if time.time() - start_time >= duration_seconds:
                            break

                        if line.startswith("data: "):
                            event_count += 1

                        # Small delay to avoid tight loop
                        if event_count % 10 == 0:
                            await asyncio.sleep(0.1)

                    # If we made it through the duration without disconnect, it's a success
                    elapsed = time.time() - start_time
                    if elapsed >= duration_seconds * 0.9:  # Allow 10% variance
                        return True
                    else:
                        metrics.sse_connections_dropped += 1
                        return False

        except Exception as e:
            metrics.sse_connections_dropped += 1
            print(f"SSE stream error: {e}")
            return False

    async def http_load_test(self, num_requests: int = 200) -> TestMetrics:
        """Simulate concurrent HTTP requests."""
        print(f"\n{'='*60}")
        print(f"HTTP Load Test: {num_requests} concurrent requests")
        print(f"{'='*60}")

        metrics = TestMetrics()
        metrics.start_time = time.time()

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            # Create assistant and thread once
            assistant_id = await self.create_assistant(client)
            if not assistant_id:
                print("Failed to create assistant, aborting test")
                return metrics

            thread_id = await self.create_thread(client, assistant_id)
            if not thread_id:
                print("Failed to create thread, aborting test")
                return metrics

            print(f"Created assistant: {assistant_id}")
            print(f"Created thread: {thread_id}")
            print(f"Starting {num_requests} concurrent requests...")

            # Create tasks for concurrent requests
            tasks = []
            for i in range(num_requests):
                task = self._single_http_request(client, thread_id, assistant_id, metrics, i)
                tasks.append(task)

            # Execute all requests concurrently
            await asyncio.gather(*tasks, return_exceptions=True)

        metrics.end_time = time.time()
        return metrics

    async def _single_http_request(self, client: httpx.AsyncClient, thread_id: str,
                                   assistant_id: str, metrics: TestMetrics, request_num: int):
        """Execute a single HTTP request."""
        try:
            run_id, response_time = await self.create_run(client, thread_id, assistant_id)
            if run_id:
                metrics.record_success(response_time)
                if request_num % 50 == 0:
                    print(f"  Progress: {request_num}/{metrics.total_requests} requests completed")
            else:
                metrics.record_failure("http_error", "Failed to create run")
        except httpx.TimeoutException as e:
            metrics.record_failure("timeout", str(e))
        except httpx.ConnectError as e:
            metrics.record_failure("connection", str(e))
        except Exception as e:
            metrics.record_failure("unknown", str(e))

    async def sse_load_test(self, num_streams: int = 90, duration_seconds: int = 900) -> TestMetrics:
        """Simulate concurrent SSE streams."""
        print(f"\n{'='*60}")
        print(f"SSE Load Test: {num_streams} concurrent streams for {duration_seconds}s")
        print(f"{'='*60}")

        metrics = TestMetrics()
        metrics.start_time = time.time()

        # Setup: Create assistant, threads, and runs
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            assistant_id = await self.create_assistant(client)
            if not assistant_id:
                print("Failed to create assistant, aborting test")
                return metrics

            print(f"Created assistant: {assistant_id}")
            print(f"Creating {num_streams} threads and runs...")

            stream_configs = []
            for i in range(num_streams):
                thread_id = await self.create_thread(client, assistant_id)
                if not thread_id:
                    continue

                run_id, _ = await self.create_run(client, thread_id, assistant_id)
                if not run_id:
                    continue

                stream_configs.append((thread_id, run_id))

                if (i + 1) % 10 == 0:
                    print(f"  Created {i + 1}/{num_streams} streams...")

        print(f"Starting {len(stream_configs)} concurrent SSE streams...")

        # Open all SSE streams concurrently
        tasks = []
        for thread_id, run_id in stream_configs:
            task = self.stream_run(thread_id, run_id, duration_seconds, metrics)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful streams
        for result in results:
            if isinstance(result, bool) and result:
                metrics.record_success(duration_seconds)
            elif isinstance(result, Exception):
                metrics.record_failure("sse_error", str(result))

        metrics.end_time = time.time()
        return metrics

    async def mixed_load_test(self, num_sse_streams: int = 90,
                             num_http_requests: int = 100,
                             duration_minutes: int = 10) -> TestMetrics:
        """Simulate realistic mixed load."""
        print(f"\n{'='*60}")
        print(f"Mixed Load Test: {num_sse_streams} SSE + {num_http_requests} HTTP for {duration_minutes}min")
        print(f"{'='*60}")

        metrics = TestMetrics()
        metrics.start_time = time.time()

        # Start SSE streams
        sse_task = asyncio.create_task(
            self.sse_load_test(num_sse_streams, duration_minutes * 60)
        )

        # Wait a bit for SSE streams to establish
        await asyncio.sleep(5)

        # Start HTTP load in parallel
        http_task = asyncio.create_task(
            self.http_load_test(num_http_requests)
        )

        # Wait for both to complete
        sse_metrics, http_metrics = await asyncio.gather(sse_task, http_task)

        # Merge metrics
        metrics.total_requests = sse_metrics.total_requests + http_metrics.total_requests
        metrics.successful_requests = sse_metrics.successful_requests + http_metrics.successful_requests
        metrics.failed_requests = sse_metrics.failed_requests + http_metrics.failed_requests
        metrics.timeout_errors = sse_metrics.timeout_errors + http_metrics.timeout_errors
        metrics.connection_errors = sse_metrics.connection_errors + http_metrics.connection_errors
        metrics.pool_exhausted_errors = sse_metrics.pool_exhausted_errors + http_metrics.pool_exhausted_errors
        metrics.sse_connections_opened = sse_metrics.sse_connections_opened
        metrics.sse_connections_dropped = sse_metrics.sse_connections_dropped
        metrics.response_times = sse_metrics.response_times + http_metrics.response_times
        metrics.errors = sse_metrics.errors + http_metrics.errors

        metrics.end_time = time.time()
        return metrics


async def main():
    """Run load tests."""
    # Configuration
    base_url = os.getenv("AEGRA_URL", "http://localhost:8000")
    token = os.getenv("AEGRA_TOKEN")

    print(f"\n{'='*60}")
    print(f"Aegra Load Testing Tool")
    print(f"{'='*60}")
    print(f"Server: {base_url}")
    print(f"Auth: {'Enabled' if token else 'Disabled (noop)'}")
    print(f"{'='*60}\n")

    tester = LoadTester(base_url, token)

    # Health check
    if not await tester.health_check():
        print("\nServer health check failed. Make sure the server is running.")
        print("Start server with: docker compose up -d")
        sys.exit(1)

    # Test menu
    print("\nSelect test scenario:")
    print("1. HTTP Load Test (200 concurrent requests)")
    print("2. SSE Load Test (90 concurrent streams for 15 minutes)")
    print("3. Quick SSE Test (10 streams for 2 minutes)")
    print("4. Mixed Load Test (90 SSE + 100 HTTP for 10 minutes)")
    print("5. Quick Mixed Test (10 SSE + 50 HTTP for 2 minutes)")
    print("6. Run all tests (except long-running ones)")

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == "1":
        metrics = await tester.http_load_test(200)
        metrics.print_summary("HTTP Load Test (200 requests)")

    elif choice == "2":
        metrics = await tester.sse_load_test(90, 900)
        metrics.print_summary("SSE Load Test (90 streams, 15min)")

    elif choice == "3":
        metrics = await tester.sse_load_test(10, 120)
        metrics.print_summary("Quick SSE Test (10 streams, 2min)")

    elif choice == "4":
        metrics = await tester.mixed_load_test(90, 100, 10)
        metrics.print_summary("Mixed Load Test (90 SSE + 100 HTTP, 10min)")

    elif choice == "5":
        metrics = await tester.mixed_load_test(10, 50, 2)
        metrics.print_summary("Quick Mixed Test (10 SSE + 50 HTTP, 2min)")

    elif choice == "6":
        print("\nRunning comprehensive test suite...")

        # Test 1: HTTP load
        metrics1 = await tester.http_load_test(200)
        metrics1.print_summary("Test 1: HTTP Load (200 requests)")

        # Test 2: Quick SSE
        metrics2 = await tester.sse_load_test(10, 120)
        metrics2.print_summary("Test 2: Quick SSE (10 streams, 2min)")

        # Test 3: Quick mixed
        metrics3 = await tester.mixed_load_test(10, 50, 2)
        metrics3.print_summary("Test 3: Quick Mixed (10 SSE + 50 HTTP, 2min)")

        print("\nAll tests complete!")

    else:
        print("Invalid choice")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
