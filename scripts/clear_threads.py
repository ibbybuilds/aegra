#!/usr/bin/env python3
"""Script to delete all threads using the API."""

import asyncio
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install it with: pip install httpx")
    sys.exit(1)

try:
    from langgraph_sdk import get_client
except ImportError:
    print(
        "Error: langgraph-sdk is required. Install it with: pip install langgraph-sdk"
    )
    sys.exit(1)

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def delete_all_threads(server_url: str, confirm: bool = False):
    """Delete all threads for the current user via the API."""
    # Use SDK client for deletion (it works), but HTTP for listing
    client = get_client(url=server_url)

    print(f"Connecting to server: {server_url}")

    # List all threads using direct HTTP request (SDK doesn't expose list method)
    print("\nFetching threads...")
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(f"{server_url}/threads")
            response.raise_for_status()
            threads_response = response.json()
            threads = threads_response.get("threads", [])
            total = threads_response.get("total", len(threads))
    except httpx.HTTPStatusError as e:
        print(
            f"HTTP error fetching threads: {e.response.status_code} - {e.response.text}"
        )
        return False
    except Exception as e:
        print(f"Error fetching threads: {e}")
        return False

    if total == 0:
        print("No threads found. Nothing to delete.")
        return True

    print(f"Found {total} thread(s)")

    # Show thread IDs
    if threads:
        print("\nThread IDs:")
        for thread in threads:
            thread_id = thread.get("thread_id", "unknown")
            status = thread.get("status", "unknown")
            created_at = thread.get("created_at", "unknown")
            print(f"  - {thread_id} (status: {status}, created: {created_at})")

    # Confirm deletion
    if not confirm:
        print(f"\nWARNING: This will delete {total} thread(s) and all associated runs.")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Deletion cancelled.")
            return False

    # Delete each thread
    print(f"\nDeleting {total} thread(s)...")
    deleted_count = 0
    failed_count = 0

    for i, thread in enumerate(threads, 1):
        thread_id = thread.get("thread_id", "unknown")
        print(f"[{i}/{total}] Deleting thread {thread_id}...", end=" ", flush=True)

        try:
            await client.threads.delete(thread_id)
            print("Deleted")
            deleted_count += 1
        except Exception as e:
            print(f"Failed: {e}")
            failed_count += 1

    # Summary
    print(f"\n{'=' * 50}")
    print("Summary:")
    print(f"  Total threads: {total}")
    print(f"  Deleted: {deleted_count}")
    print(f"  Failed: {failed_count}")
    print(f"{'=' * 50}")

    return failed_count == 0


def main():
    """Main function."""
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    confirm = "--yes" in sys.argv or "-y" in sys.argv

    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Delete All Threads Script

Usage:
  python scripts/clear_threads.py [options]

Options:
  --yes, -y     Skip confirmation prompt
  --help, -h    Show this help message

Environment Variables:
  SERVER_URL    Server URL (default: http://localhost:8000)

Examples:
  python scripts/clear_threads.py
  python scripts/clear_threads.py --yes
  SERVER_URL=http://localhost:8080 python scripts/clear_threads.py
        """)
        return

    print("Thread Cleanup Script")
    print(f"Server URL: {server_url}\n")

    try:
        success = asyncio.run(delete_all_threads(server_url, confirm=confirm))
        if success:
            print("\nAll threads deleted successfully!")
            sys.exit(0)
        else:
            print(
                "\nWARNING: Some threads could not be deleted. Check the errors above."
            )
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nWARNING: Interrupted by user. Some threads may have been deleted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
