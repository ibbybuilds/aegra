"""
Real-time capacity monitoring for Aegra server during load tests.

Monitors:
- Database connection pool usage
- Docker container stats (CPU, memory)
- Server health status

Usage:
    # Monitor local Docker setup
    python scripts/monitor_capacity.py

    # Monitor with custom refresh interval
    python scripts/monitor_capacity.py --interval 5

Requirements:
    - docker (for container stats)
    - psycopg2-binary (for database queries)
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

try:
    import psycopg2
except ImportError:
    print("Warning: psycopg2 not installed. Database monitoring disabled.")
    print("Install with: uv pip install psycopg2-binary")
    psycopg2 = None


class CapacityMonitor:
    """Monitor Aegra server capacity metrics."""

    def __init__(self, database_url: Optional[str] = None, interval: int = 3):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://user:password@localhost:5432/aegra"
        )
        self.interval = interval
        self.running = False

    def get_docker_stats(self) -> dict:
        """Get Docker container stats for aegra service."""
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format",
                 "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if 'aegra' in line.lower():
                        parts = line.split('\t')
                        if len(parts) >= 4:
                            return {
                                "container": parts[0],
                                "cpu_percent": parts[1],
                                "memory_usage": parts[2],
                                "memory_percent": parts[3]
                            }
            return {"error": "Aegra container not found"}

        except subprocess.TimeoutExpired:
            return {"error": "Docker stats timeout"}
        except FileNotFoundError:
            return {"error": "Docker not installed"}
        except Exception as e:
            return {"error": str(e)}

    def get_database_connections(self) -> dict:
        """Get current database connection count."""
        if not psycopg2:
            return {"error": "psycopg2 not installed"}

        try:
            # Convert asyncpg URL to psycopg2 format
            db_url = self.database_url.replace("+asyncpg", "")

            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()

            # Get active connections
            cursor.execute("""
                SELECT count(*) as total,
                       count(*) FILTER (WHERE state = 'active') as active,
                       count(*) FILTER (WHERE state = 'idle') as idle,
                       count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            return {
                "total": result[0],
                "active": result[1],
                "idle": result[2],
                "idle_in_transaction": result[3]
            }

        except Exception as e:
            return {"error": str(e)}

    def print_status(self):
        """Print current status."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Clear screen (works on Unix-like systems)
        print("\033[2J\033[H", end="")

        print(f"{'='*70}")
        print(f"Aegra Capacity Monitor - {timestamp}")
        print(f"{'='*70}\n")

        # Docker stats
        docker_stats = self.get_docker_stats()
        print("Docker Container Stats:")
        if "error" not in docker_stats:
            print(f"  Container: {docker_stats['container']}")
            print(f"  CPU Usage: {docker_stats['cpu_percent']}")
            print(f"  Memory: {docker_stats['memory_usage']} ({docker_stats['memory_percent']})")
        else:
            print(f"  Error: {docker_stats['error']}")

        print()

        # Database connections
        db_stats = self.get_database_connections()
        print("Database Connections:")
        if "error" not in db_stats:
            print(f"  Total: {db_stats['total']}")
            print(f"  Active: {db_stats['active']}")
            print(f"  Idle: {db_stats['idle']}")
            print(f"  Idle in Transaction: {db_stats['idle_in_transaction']}")

            # Calculate utilization based on configured pool
            pool_size = int(os.getenv("DB_POOL_SIZE", "30"))
            max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
            max_connections = pool_size + max_overflow

            utilization = (db_stats['total'] / max_connections) * 100
            print(f"\n  Pool Configuration: {pool_size} + {max_overflow} overflow = {max_connections} max")
            print(f"  Utilization: {utilization:.1f}%")

            if utilization > 90:
                print("  WARNING: Pool utilization > 90%")
            elif utilization > 75:
                print("  CAUTION: Pool utilization > 75%")
        else:
            print(f"  Error: {db_stats['error']}")

        print(f"\n{'='*70}")
        print(f"Refreshing every {self.interval}s... (Press Ctrl+C to stop)")

    async def monitor(self):
        """Start monitoring loop."""
        self.running = True
        print("Starting capacity monitor...\n")

        while self.running:
            try:
                self.print_status()
                await asyncio.sleep(self.interval)
            except KeyboardInterrupt:
                break

        print("\n\nMonitoring stopped.")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor Aegra server capacity during load tests"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Refresh interval in seconds (default: 3)"
    )
    parser.add_argument(
        "--database-url",
        type=str,
        help="Database URL (default: from DATABASE_URL env var)"
    )

    args = parser.parse_args()

    monitor = CapacityMonitor(
        database_url=args.database_url,
        interval=args.interval
    )

    try:
        asyncio.run(monitor.monitor())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
