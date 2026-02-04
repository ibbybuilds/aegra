"""
Simple infrastructure load test for Aegra capacity validation.

Tests HTTP concurrency and connection handling without requiring graph execution.

Usage:
    python scripts/simple_load_test.py
"""

import asyncio
import time
from datetime import datetime
from typing import List

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: uv pip install httpx")
    exit(1)


async def test_concurrent_http(url: str, num_requests: int = 200):
    """Test concurrent HTTP requests."""
    print(f"\n{'='*60}")
    print(f"Testing {num_requests} concurrent HTTP requests")
    print(f"{'='*60}")

    start_time = time.time()
    successful = 0
    failed = 0
    response_times = []

    async def make_request(client, i):
        nonlocal successful, failed
        try:
            req_start = time.time()
            response = await client.get(f"{url}/assistants")
            req_time = time.time() - req_start

            if response.status_code == 200:
                successful += 1
                response_times.append(req_time)
            else:
                failed += 1

            if (i + 1) % 50 == 0:
                print(f"  Completed: {i + 1}/{num_requests}")

        except Exception as e:
            failed += 1
            if failed <= 5:  # Only print first 5 errors
                print(f"  Error: {e}")

    # Create all requests concurrently
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [make_request(client, i) for i in range(num_requests)]
        await asyncio.gather(*tasks, return_exceptions=True)

    duration = time.time() - start_time
    success_rate = (successful / num_requests * 100) if num_requests > 0 else 0

    print(f"\nResults:")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Total: {num_requests}")
    print(f"  Successful: {successful} ({success_rate:.1f}%)")
    print(f"  Failed: {failed}")
    print(f"  Requests/sec: {num_requests/duration:.2f}")

    if response_times:
        sorted_times = sorted(response_times)
        print(f"\nResponse Times:")
        print(f"  Min: {min(sorted_times):.3f}s")
        print(f"  Max: {max(sorted_times):.3f}s")
        print(f"  Mean: {sum(sorted_times)/len(sorted_times):.3f}s")
        print(f"  p50: {sorted_times[int(len(sorted_times)*0.5)]:.3f}s")
        print(f"  p95: {sorted_times[int(len(sorted_times)*0.95)]:.3f}s")
        print(f"  p99: {sorted_times[int(len(sorted_times)*0.99)]:.3f}s")

    return successful, failed, duration


async def test_health_endpoint(url: str):
    """Test health endpoint is responsive."""
    print(f"\n{'='*60}")
    print(f"Testing Health Endpoint")
    print(f"{'='*60}")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Server is healthy")
                print(f"  Status: {data.get('status')}")
                print(f"  Database: {data.get('database')}")
                print(f"  Redis: {data.get('redis')}")
                return True
            else:
                print(f"✗ Health check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


async def test_database_pool_stress(url: str, num_parallel: int = 150):
    """Test database connection pool under load."""
    print(f"\n{'='*60}")
    print(f"Testing Database Pool ({num_parallel} parallel connections)")
    print(f"{'='*60}")

    start_time = time.time()
    successful = 0
    failed = 0
    pool_errors = 0

    async def query_database(client, i):
        nonlocal successful, failed, pool_errors
        try:
            # GET /assistants hits the database
            response = await client.get(f"{url}/assistants")

            if response.status_code == 200:
                successful += 1
            elif "pool" in response.text.lower():
                pool_errors += 1
                failed += 1
            else:
                failed += 1

        except Exception as e:
            failed += 1
            if "pool" in str(e).lower():
                pool_errors += 1

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [query_database(client, i) for i in range(num_parallel)]
        await asyncio.gather(*tasks, return_exceptions=True)

    duration = time.time() - start_time
    success_rate = (successful / num_parallel * 100) if num_parallel > 0 else 0

    print(f"\nResults:")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Successful: {successful}/{num_parallel} ({success_rate:.1f}%)")
    print(f"  Failed: {failed}")
    print(f"  Pool exhausted errors: {pool_errors}")

    if pool_errors > 0:
        print(f"\n⚠ WARNING: Database pool exhausted!")
        print(f"   Consider increasing DB_POOL_SIZE or DB_MAX_OVERFLOW")
    else:
        print(f"\n✓ Database pool handled load successfully")

    return successful, failed, pool_errors


async def main():
    url = "http://localhost:8000"

    print(f"\n{'='*60}")
    print(f"Aegra Simple Load Test")
    print(f"{'='*60}")
    print(f"Server: {url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Test 1: Health check
    healthy = await test_health_endpoint(url)
    if not healthy:
        print("\n❌ Server not healthy, aborting tests")
        return

    # Test 2: Moderate HTTP load (100 requests)
    await test_concurrent_http(url, 100)

    # Test 3: High HTTP load (300 requests - target capacity)
    await test_concurrent_http(url, 300)

    # Test 4: Database pool stress test
    await test_database_pool_stress(url, 150)

    # Final summary
    print(f"\n{'='*60}")
    print(f"Load Testing Complete!")
    print(f"{'='*60}")
    print(f"\nCapacity Targets:")
    print(f"  ✓ 300 concurrent HTTP connections - TESTED")
    print(f"  ⚠ 90 concurrent SSE streams - REQUIRES VALID GRAPH")
    print(f"  ✓ Database pool (200 max) - TESTED")
    print(f"\nNext Steps:")
    print(f"  1. Review results above")
    print(f"  2. Check Docker stats: docker stats")
    print(f"  3. Check DB connections: docker compose exec postgres \\")
    print(f"     psql -U user -d aegra -c \"SELECT count(*) FROM pg_stat_activity;\"")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(0)
