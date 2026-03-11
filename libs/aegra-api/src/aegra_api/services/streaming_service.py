"""Streaming service for orchestrating SSE streaming."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from aegra_api.core.sse import create_error_event
from aegra_api.models import Run
from aegra_api.services.broker import broker_manager
from aegra_api.services.event_converter import EventConverter
from aegra_api.utils import extract_event_sequence, generate_event_id

logger = structlog.getLogger(__name__)


class StreamingService:
    """Service to handle SSE streaming orchestration.

    Events flow through the broker which handles both live broadcast
    and replay storage. No separate event store needed.
    """

    def __init__(self) -> None:
        self.event_counters: dict[str, int] = {}
        self.event_converter = EventConverter()

    def _next_event_counter(self, run_id: str, event_id: str) -> int:
        """Update and return the next event counter for a run."""
        try:
            idx = self._extract_event_sequence(event_id)
            current = self.event_counters.get(run_id, 0)
            if idx > current:
                self.event_counters[run_id] = idx
                return idx
        except ValueError:
            logger.warning(f"Event counter update failed for event_id: {event_id}")
        return self.event_counters.get(run_id, 0)

    async def put_to_broker(
        self,
        run_id: str,
        event_id: str,
        raw_event: Any,
    ) -> None:
        """Put an event into the run's broker for live consumers and replay storage."""
        broker = broker_manager.get_or_create_broker(run_id)
        self._next_event_counter(run_id, event_id)
        await broker.put(event_id, raw_event)

    async def signal_run_cancelled(self, run_id: str) -> None:
        """Signal that a run was cancelled."""
        broker = broker_manager.get_broker(run_id)
        if broker is None or broker.is_finished():
            return

        counter = self.event_counters.get(run_id, 0) + 1
        self.event_counters[run_id] = counter
        event_id = generate_event_id(run_id, counter)

        await broker.put(event_id, ("end", {"status": "interrupted"}))
        broker_manager.cleanup_broker(run_id)

    async def signal_run_error(self, run_id: str, error_message: str, error_type: str = "Error") -> None:
        """Signal that a run encountered an error.

        Sends a proper 'error' event to the broker followed by an 'end' event.
        Uses get_broker (not get_or_create) to avoid creating a new broker for
        a run that already finished, which would cause duplicate error events.
        """
        broker = broker_manager.get_broker(run_id)
        if broker is None or broker.is_finished():
            return

        counter = self.event_counters.get(run_id, 0) + 1
        self.event_counters[run_id] = counter
        error_event_id = generate_event_id(run_id, counter)

        error_payload = {"error": error_type, "message": error_message}

        await broker.put(error_event_id, ("error", error_payload))

        counter += 1
        self.event_counters[run_id] = counter
        end_event_id = generate_event_id(run_id, counter)
        await broker.put(end_event_id, ("end", {"status": "error"}))
        broker_manager.cleanup_broker(run_id)

    def _extract_event_sequence(self, event_id: str) -> int:
        """Extract numeric sequence from event_id format: {run_id}_event_{sequence}."""
        return extract_event_sequence(event_id)

    async def stream_run_execution(
        self,
        run: Run,
        last_event_id: str | None = None,
        cancel_on_disconnect: bool = False,
    ) -> AsyncIterator[str]:
        """Stream run execution with unified producer-consumer pattern."""
        run_id = run.run_id
        try:
            # Replay stored events first
            last_sent_sequence = 0
            if last_event_id:
                last_sent_sequence = self._extract_event_sequence(last_event_id)

            async for sse_event in self._replay_stored_events(run_id, last_event_id):
                yield sse_event

            # Stream live events if run is still active
            async for sse_event in self._stream_live_events(run, last_sent_sequence):
                yield sse_event

        except asyncio.CancelledError:
            logger.debug(f"Stream cancelled for run {run_id}")
            if cancel_on_disconnect:
                self._cancel_background_task(run_id)
            raise
        except Exception as e:
            logger.error(f"Error in stream_run_execution for run {run_id}: {e}")
            yield create_error_event(str(e))

    async def _replay_stored_events(self, run_id: str, last_event_id: str | None) -> AsyncIterator[str]:
        """Replay stored events from the broker's replay buffer."""
        broker = broker_manager.get_or_create_broker(run_id)
        stored_events = await broker.replay(last_event_id)

        for event_id, raw_event in stored_events:
            sse_event = await self._convert_raw_to_sse(event_id, raw_event)
            if sse_event:
                yield sse_event

    async def _stream_live_events(self, run: Run, last_sent_sequence: int) -> AsyncIterator[str]:
        """Stream live events from broker."""
        run_id = run.run_id
        broker = broker_manager.get_broker(run_id)

        # If run is in a terminal state and broker is either missing or finished,
        # there are no live events to stream. Using get_broker (not get_or_create)
        # avoids creating a blank broker that would hang forever in aiter().
        if run.status in ["success", "error", "interrupted"] and (broker is None or broker.is_finished()):
            return

        if broker is None:
            broker = broker_manager.get_or_create_broker(run_id)

        async for event_id, raw_event in broker.aiter():
            # Skip duplicates that were already replayed
            current_sequence = self._extract_event_sequence(event_id)
            if current_sequence <= last_sent_sequence:
                continue

            sse_event = await self._convert_raw_to_sse(event_id, raw_event)
            if sse_event:
                yield sse_event
                last_sent_sequence = current_sequence

    def _cancel_background_task(self, run_id: str) -> bool:
        """Cancel the asyncio task for a run."""
        try:
            from aegra_api.api.runs import active_runs

            task = active_runs.get(run_id)
            if task and not task.done():
                logger.info(f"Cancelling asyncio task for run {run_id}")
                task.cancel()
                return True
            elif task and task.done():
                logger.debug(f"Task for run {run_id} already completed")
                return False
            else:
                logger.debug(f"No active task found for run {run_id}")
                return False
        except Exception as e:
            logger.warning(f"Failed to cancel background task for run {run_id}: {e}")
            return False

    async def _convert_raw_to_sse(self, event_id: str, raw_event: Any) -> str | None:
        """Convert a raw event from broker to SSE format."""
        return self.event_converter.convert_raw_to_sse(event_id, raw_event)

    async def interrupt_run(self, run_id: str) -> bool:
        """Interrupt a running execution."""
        try:
            self._cancel_background_task(run_id)
            await self.signal_run_error(run_id, "Run was interrupted")
            return True
        except Exception as e:
            logger.error(f"Error interrupting run {run_id}: {e}")
            return False

    async def cancel_run(self, run_id: str) -> bool:
        """Cancel a pending or running execution."""
        try:
            self._cancel_background_task(run_id)
            await self.signal_run_cancelled(run_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelling run {run_id}: {e}")
            return False

    def is_run_streaming(self, run_id: str) -> bool:
        """Check if run is currently active (has a broker)."""
        broker = broker_manager.get_broker(run_id)
        return broker is not None and not broker.is_finished()

    async def cleanup_run(self, run_id: str) -> None:
        """Clean up streaming resources for a run."""
        broker_manager.cleanup_broker(run_id)


# Global streaming service instance
streaming_service = StreamingService()
