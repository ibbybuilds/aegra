"""Persistent event store for SSE replay functionality (Postgres-backed)."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from ..core.database import db_manager
from ..core.serializers import GeneralSerializer
from ..core.sse import SSEEvent

logger = structlog.get_logger(__name__)


class EventStore:
    """Postgres-backed event store for SSE replay functionality"""

    CLEANUP_INTERVAL = 300  # seconds

    def __init__(self) -> None:
        self._cleanup_task: asyncio.Task | None = None

    async def start_cleanup_task(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    async def store_event(self, run_id: str, event: SSEEvent) -> None:
        """Persist an event with sequence extracted from id suffix.

        We expect event.id format: f"{run_id}_event_{seq}".
        """
        try:
            seq = int(str(event.id).split("_event_")[-1])
        except Exception:
            seq = 0
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            stmt = text(
                """
                INSERT INTO run_events (id, run_id, seq, event, data, created_at)
                VALUES (:id, :run_id, :seq, :event, :data, NOW())
                ON CONFLICT (id) DO NOTHING
                """
            ).bindparams(bindparam("data", type_=JSONB))
            await conn.execute(
                stmt,
                {
                    "id": event.id,
                    "run_id": run_id,
                    "seq": seq,
                    "event": event.event,
                    "data": event.data,
                },
            )

    async def get_events_since(self, run_id: str, last_event_id: str) -> list[SSEEvent]:
        """Fetch all events for run after last_event_id sequence."""
        try:
            last_seq = int(str(last_event_id).split("_event_")[-1])
        except Exception:
            last_seq = -1
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            rs = await conn.execute(
                text(
                    """
                    SELECT id, event, data, created_at
                    FROM run_events
                    WHERE run_id = :run_id AND seq > :last_seq
                    ORDER BY seq ASC
                    """
                ),
                {"run_id": run_id, "last_seq": last_seq},
            )
            rows = rs.fetchall()
        return [
            SSEEvent(id=r.id, event=r.event, data=r.data, timestamp=r.created_at)
            for r in rows
        ]

    async def get_all_events(self, run_id: str) -> list[SSEEvent]:
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            rs = await conn.execute(
                text(
                    """
                    SELECT id, event, data, created_at
                    FROM run_events
                    WHERE run_id = :run_id
                    ORDER BY seq ASC
                    """
                ),
                {"run_id": run_id},
            )
            rows = rs.fetchall()
        return [
            SSEEvent(id=r.id, event=r.event, data=r.data, timestamp=r.created_at)
            for r in rows
        ]

    async def cleanup_events(self, run_id: str) -> None:
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM run_events WHERE run_id = :run_id"),
                {"run_id": run_id},
            )

    async def get_run_info(self, run_id: str) -> dict | None:
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            rs = await conn.execute(
                text(
                    """
                    SELECT MIN(seq) AS first_seq, MAX(seq) AS last_seq
                    FROM run_events
                    WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
            row = rs.fetchone()
            if not row or row.last_seq is None:
                return None
            # Fetch last event for id and timestamp
            rs2 = await conn.execute(
                text(
                    """
                    SELECT id, created_at
                    FROM run_events
                    WHERE run_id = :run_id AND seq = :last_seq
                    LIMIT 1
                    """
                ),
                {"run_id": run_id, "last_seq": row.last_seq},
            )
            last = rs2.fetchone()
        return {
            "run_id": run_id,
            "event_count": int(row.last_seq) - int(row.first_seq) + 1
            if row.first_seq is not None
            else 0,
            "first_event_time": None,
            "last_event_time": last.created_at if last else None,
            "last_event_id": last.id if last else None,
        }

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_old_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in event store cleanup: {e}")

    async def _cleanup_old_runs(self) -> None:
        # Retain events for 1 hour by default
        engine = db_manager.get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM run_events WHERE created_at < NOW() - INTERVAL '1 hour'"
                )
            )


# Global event store instance
event_store = EventStore()


async def store_sse_event(
    run_id: str, event_id: str, event_type: str, data: dict
) -> SSEEvent:
    """Store SSE event with proper serialization"""
    serializer = GeneralSerializer()

    # Ensure JSONB-safe data by serializing complex objects
    try:
        safe_data = json.loads(json.dumps(data, default=serializer.serialize))
    except Exception:
        # Fallback to stringifying as a last resort to avoid crashing the run
        safe_data = {"raw": str(data)}
    event = SSEEvent(
        id=event_id, event=event_type, data=safe_data, timestamp=datetime.now(UTC)
    )
    await event_store.store_event(run_id, event)
    return event
