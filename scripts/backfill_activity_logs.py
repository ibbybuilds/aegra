"""
Backfill activity logs for existing runs.

This script creates activity log entries for all existing runs that were created
before the activity logging system was implemented. This provides historical
accuracy for the management dashboard metrics.

Usage:
    uv run scripts/backfill_activity_logs.py
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add libs/aegra-api/src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "libs" / "aegra-api" / "src"))

from aegra_api.core.orm import ActivityLog as ActivityLogORM
from aegra_api.core.orm import Run as RunORM

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration - use environment variable like the main app
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/aegra"
)


async def backfill_activity_logs():
    """Backfill activity logs for all existing runs."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session_maker() as session:
            # Get all runs that don't have corresponding activity logs
            runs_query = select(RunORM).order_by(RunORM.created_at)
            runs_result = await session.execute(runs_query)
            runs = runs_result.scalars().all()

            logger.info(f"Found {len(runs)} total runs to backfill")

            if not runs:
                logger.info("No runs found to backfill")
                return

            # Check which runs already have activity logs
            existing_run_ids = set()
            existing_logs_query = select(ActivityLogORM.run_id)
            existing_logs_result = await session.execute(existing_logs_query)
            for (run_id,) in existing_logs_result:
                if run_id:
                    existing_run_ids.add(run_id)

            logger.info(f"Found {len(existing_run_ids)} runs already in activity logs")

            # Backfill missing runs
            backfilled_count = 0
            for run in runs:
                if run.run_id in existing_run_ids:
                    continue

                # Create activity log entries for key run lifecycle events
                # Run started
                activity_start = ActivityLogORM(
                    user_id=run.user_id,
                    action_type="run_started",
                    assistant_id=run.assistant_id,
                    thread_id=run.thread_id,
                    run_id=run.run_id,
                    action_status="success",
                    details={
                        "backfilled": True,
                        "original_status": run.status,
                    },
                    metadata_json={
                        "backfill_timestamp": datetime.now(UTC).isoformat(),
                        "run_created_at": run.created_at.isoformat()
                        if run.created_at
                        else None,
                    },
                )
                # Set created_at to match run start time (minus 1 second for ordering)
                if run.created_at:
                    activity_start.created_at = run.created_at

                session.add(activity_start)

                # Run completed/failed based on final status
                if run.status in ["completed", "failed", "cancelled", "interrupted"]:
                    activity_end = ActivityLogORM(
                        user_id=run.user_id,
                        action_type=f"run_{run.status}",
                        assistant_id=run.assistant_id,
                        thread_id=run.thread_id,
                        run_id=run.run_id,
                        action_status=run.status,
                        details={
                            "backfilled": True,
                            "error": run.error_message,
                        },
                        metadata_json={
                            "backfill_timestamp": datetime.now(UTC).isoformat(),
                            "run_updated_at": run.updated_at.isoformat()
                            if run.updated_at
                            else None,
                        },
                    )
                    # Set created_at to match run end time
                    if run.updated_at:
                        activity_end.created_at = run.updated_at

                    session.add(activity_end)

                backfilled_count += 1

                if backfilled_count % 50 == 0:
                    logger.info(f"Backfilled {backfilled_count} runs...")

            # Commit all changes
            if backfilled_count > 0:
                await session.commit()
                logger.info(
                    f"✅ Successfully backfilled {backfilled_count} runs with activity logs"
                )
            else:
                logger.info(
                    "No new runs to backfill (all existing runs already have activity logs)"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill_activity_logs())
