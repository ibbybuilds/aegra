"""Streaming service for orchestrating SSE streaming"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from aegra_api.core.sse import create_error_event
from aegra_api.models import Run
from aegra_api.services.broker import broker_manager
from aegra_api.services.event_converter import EventConverter
from aegra_api.services.event_store import event_store, store_sse_event
from aegra_api.utils import extract_event_sequence, generate_event_id

logger = structlog.getLogger(__name__)


class StreamingService:
    """Service to handle SSE streaming orchestration"""

    def __init__(self):
        self.event_counters: dict[str, int] = {}
        self.event_converter = EventConverter()

    def _next_event_counter(self, run_id: str, event_id: str) -> int:
        """Update and return the next event counter for a run"""
        try:
            idx = self._extract_event_sequence(event_id)
            current = self.event_counters.get(run_id, 0)
            if idx > current:
                self.event_counters[run_id] = idx
                return idx
        except Exception as e:
            logger.warning(f"Event counter update failed: {e}")
        return self.event_counters.get(run_id, 0)

    async def put_to_broker(
        self,
        run_id: str,
        event_id: str,
        raw_event: Any,
    ):
        """Put an event into the run's broker queue for live consumers

        Note: Events from graph_streaming are already filtered, so they pass through as-is.
        """
        broker = broker_manager.get_or_create_broker(run_id)
        self._next_event_counter(run_id, event_id)
        await broker.put(event_id, raw_event)

    async def store_event_from_raw(
        self,
        run_id: str,
        event_id: str,
        raw_event: Any,
    ):
        """Convert raw event to stored format and store it

        Note: Events from graph_streaming are already filtered, so they pass through as-is.
        """
        processed_event = raw_event

        # Parse the processed event
        node_path = None
        stream_mode_label = None
        event_payload = None

        if isinstance(processed_event, tuple):
            if len(processed_event) == 2:
                stream_mode_label, event_payload = processed_event
            elif len(processed_event) == 3:
                node_path, stream_mode_label, event_payload = processed_event
        else:
            stream_mode_label = "values"
            event_payload = processed_event

        # Store based on stream mode
        if stream_mode_label == "messages":
            await store_sse_event(
                run_id,
                event_id,
                "messages",
                {
                    "type": "messages_stream",
                    "message_chunk": event_payload[0]
                    if isinstance(event_payload, tuple) and len(event_payload) >= 1
                    else event_payload,
                    "metadata": event_payload[1]
                    if isinstance(event_payload, tuple) and len(event_payload) >= 2
                    else None,
                    "node_path": node_path,
                },
            )
        elif stream_mode_label == "messages/partial":
            await store_sse_event(
                run_id,
                event_id,
                "messages/partial",
                {
                    "type": "messages_partial",
                    "messages": event_payload,
                    "node_path": node_path,
                },
            )
        elif stream_mode_label == "messages/complete":
            await store_sse_event(
                run_id,
                event_id,
                "messages/complete",
                {
                    "type": "messages_complete",
                    "messages": event_payload,
                    "node_path": node_path,
                },
            )
        elif stream_mode_label == "messages/metadata":
            await store_sse_event(
                run_id,
                event_id,
                "messages/metadata",
                {
                    "type": "messages_metadata",
                    "metadata": event_payload,
                    "node_path": node_path,
                },
            )
        elif stream_mode_label == "events":
            await store_sse_event(
                run_id,
                event_id,
                "events",
                {
                    "type": "langchain_event",
                    "event": event_payload,
                },
            )
        elif stream_mode_label == "values" or stream_mode_label == "updates":
            await store_sse_event(
                run_id,
                event_id,
                "values",
                {"type": "execution_values", "chunk": event_payload},
            )
        elif stream_mode_label == "end":
            await store_sse_event(
                run_id,
                event_id,
                "end",
                {
                    "type": "run_complete",
                    "status": event_payload.get("status", "success"),
                    "final_output": event_payload.get("final_output"),
                },
            )
        # Add other stream modes as needed

    async def signal_run_cancelled(self, run_id: str):
        """Signal that a run was cancelled"""
        counter = self.event_counters.get(run_id, 0) + 1
        self.event_counters[run_id] = counter
        event_id = generate_event_id(run_id, counter)

        broker = broker_manager.get_or_create_broker(run_id)
        if broker:
            await broker.put(event_id, ("end", {"status": "interrupted"}))

        broker_manager.cleanup_broker(run_id)

    async def signal_run_error(self, run_id: str, error_message: str, error_type: str = "Error"):
        """Signal that a run encountered an error.

        Sends a proper 'error' event to the broker and stores it for replay.
        Also sends an 'end' event to signal stream completion.

        Args:
            run_id: The run ID.
            error_message: Human-readable error message.
            error_type: Error type/class name (e.g., "ValueError", "GraphRecursionError").
        """
        counter = self.event_counters.get(run_id, 0) + 1
        self.event_counters[run_id] = counter
        error_event_id = generate_event_id(run_id, counter)

        # Create structured error payload
        error_payload = {"error": error_type, "message": error_message}

        broker = broker_manager.get_or_create_broker(run_id)
        if broker:
            # Send dedicated error event (so frontend receives the error details)
            await broker.put(error_event_id, ("error", error_payload))

            # Store error event for replay support
            await store_sse_event(
                run_id,
                error_event_id,
                "error",
                {"error": error_type, "message": error_message},
            )

            # Send end event to signal stream completion
            counter += 1
            self.event_counters[run_id] = counter
            end_event_id = generate_event_id(run_id, counter)
            await broker.put(end_event_id, ("end", {"status": "error"}))

        broker_manager.cleanup_broker(run_id)

    def _extract_event_sequence(self, event_id: str) -> int:
        """Extract numeric sequence from event_id format: {run_id}_event_{sequence}"""
        return extract_event_sequence(event_id)

    async def stream_run_execution(
        self,
        run: Run,
        last_event_id: str | None = None,
        cancel_on_disconnect: bool = False,
    ) -> AsyncIterator[str]:
        """Stream run execution with unified producer-consumer pattern"""
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
        """Replay stored events"""
        if last_event_id:
            stored_events = await event_store.get_events_since(run_id, last_event_id)
        else:
            stored_events = await event_store.get_all_events(run_id)

        for ev in stored_events:
            sse_event = self._stored_event_to_sse(run_id, ev)
            if sse_event:
                yield sse_event

    async def _stream_live_events(self, run: Run, last_sent_sequence: int) -> AsyncIterator[str]:
        """Stream live events from broker"""
        run_id = run.run_id
        broker = broker_manager.get_or_create_broker(run_id)

        # If run finished and broker is done, nothing to stream
        if run.status in ["success", "error", "interrupted"] and broker.is_finished():
            return

        # Stream live events
        if broker:
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
        """Cancel the asyncio task for a run.

        @param run_id: The ID of the run to cancel.
        @return: True if task was cancelled, False otherwise.
        """
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
        """Convert a raw event from broker to SSE format"""
        return self.event_converter.convert_raw_to_sse(event_id, raw_event)

    async def interrupt_run(self, run_id: str) -> bool:
        """Interrupt a running execution.

        Cancels the asyncio task and signals interruption to broker.
        The task's CancelledError handler will set status to 'interrupted'.
        """
        try:
            # Cancel the asyncio task first so it stops processing
            self._cancel_background_task(run_id)
            # Signal interruption to broker for any connected clients
            await self.signal_run_error(run_id, "Run was interrupted")
            return True
        except Exception as e:
            logger.error(f"Error interrupting run {run_id}: {e}")
            return False

    async def cancel_run(self, run_id: str) -> bool:
        """Cancel a pending or running execution.

        Cancels the asyncio task and signals cancellation to broker.
        The task's CancelledError handler will set status to 'interrupted'.
        """
        try:
            # Cancel the asyncio task first so it stops processing
            self._cancel_background_task(run_id)
            # Signal cancellation to broker for any connected clients
            await self.signal_run_cancelled(run_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelling run {run_id}: {e}")
            return False

    async def _update_run_status(self, run_id: str, status: str, output: Any = None, error: str = None):
        """Update run status in database using the shared updater."""
        try:
            # Lazy import to avoid cycles
            from aegra_api.api.runs import update_run_status

            await update_run_status(run_id, status, output, error)
        except Exception as e:
            logger.error(f"Error updating run status for {run_id}: {e}")

    def is_run_streaming(self, run_id: str) -> bool:
        """Check if run is currently active (has a broker)"""
        broker = broker_manager.get_broker(run_id)
        return broker is not None and not broker.is_finished()

    async def cleanup_run(self, run_id: str):
        """Clean up streaming resources for a run"""
        broker_manager.cleanup_broker(run_id)

    def _stored_event_to_sse(self, run_id: str, ev) -> str | None:
        """Convert stored event object to SSE string"""
        return self.event_converter.convert_stored_to_sse(ev, run_id)


# Global streaming service instance
streaming_service = StreamingService()
