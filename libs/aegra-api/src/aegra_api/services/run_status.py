"""Run and thread status management.

Provides the database-level status update operations used by both the
API layer (cancel, interrupt) and the execution layer (run_executor,
worker_executor). Extracted from api/runs.py to eliminate the circular
dependency where service code imported from the API module.
"""

from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import Run as RunORM
from aegra_api.core.orm import Thread as ThreadORM
from aegra_api.core.orm import _get_session_maker
from aegra_api.core.serializers import GeneralSerializer
from aegra_api.utils.status_compat import validate_run_status, validate_thread_status

logger = structlog.getLogger(__name__)
_serializer = GeneralSerializer()


async def update_run_status(
    run_id: str,
    status: str,
    *,
    output: Any = None,
    error: str | None = None,
) -> None:
    """Persist a run's status to the database.

    Opens a short-lived session to avoid holding a connection during
    long-running graph execution.
    """
    validated = validate_run_status(status)
    maker = _get_session_maker()
    async with maker() as session:
        values: dict[str, Any] = {
            "status": validated,
            "updated_at": datetime.now(UTC),
        }
        if output is not None:
            values["output"] = _safe_serialize(output, run_id)
        if error is not None:
            values["error_message"] = error

        logger.info("Updating run status", run_id=run_id, status=validated)
        await session.execute(update(RunORM).where(RunORM.run_id == run_id).values(**values))
        await session.commit()


async def set_thread_status(session: AsyncSession, thread_id: str, status: str) -> None:
    """Update a thread's status column.

    Uses the caller's session so thread and run updates can share
    a transaction when needed.
    """
    validated = validate_thread_status(status)
    result = cast(
        CursorResult,
        await session.execute(
            update(ThreadORM)
            .where(ThreadORM.thread_id == thread_id)
            .values(status=validated, updated_at=datetime.now(UTC))
        ),
    )
    await session.commit()

    if result.rowcount == 0:
        raise ValueError(f"Thread '{thread_id}' not found")


async def finalize_run(
    run_id: str,
    thread_id: str,
    *,
    status: str,
    thread_status: str,
    output: Any = None,
    error: str | None = None,
) -> None:
    """Update run status + thread status in a single transaction.

    Batches two UPDATE statements into one DB round-trip instead of
    opening separate sessions for update_run_status and set_thread_status.
    """
    validated_run = validate_run_status(status)
    validated_thread = validate_thread_status(thread_status)
    maker = _get_session_maker()

    run_values: dict[str, Any] = {
        "status": validated_run,
        "updated_at": datetime.now(UTC),
    }
    if output is not None:
        run_values["output"] = _safe_serialize(output, run_id)
    if error is not None:
        run_values["error_message"] = error

    async with maker() as session:
        await session.execute(update(RunORM).where(RunORM.run_id == run_id).values(**run_values))
        await session.execute(
            update(ThreadORM)
            .where(ThreadORM.thread_id == thread_id)
            .values(status=validated_thread, updated_at=datetime.now(UTC))
        )
        await session.commit()

    logger.info("Finalized run", run_id=run_id, status=validated_run, thread_status=validated_thread)


def _safe_serialize(output: Any, run_id: str) -> Any:
    """Serialize output with a fallback for non-JSON-compatible objects."""
    try:
        return _serializer.serialize(output)
    except Exception as exc:
        logger.warning("Output serialization failed", run_id=run_id, error=str(exc))
        return {
            "error": "Output serialization failed",
            "original_type": str(type(output)),
        }
