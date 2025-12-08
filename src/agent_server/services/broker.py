"""Event broker for managing run-specific event queues"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import structlog

from .base_broker import BaseBrokerManager, BaseRunBroker

logger = structlog.getLogger(__name__)


class RunBroker(BaseRunBroker):
    """Manages event queuing and distribution for a specific run"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.finished = asyncio.Event()
        self._created_at = asyncio.get_event_loop().time()

    async def put(self, event_id: str, payload: Any) -> None:
        """Put an event into the broker queue"""
        if self.finished.is_set():
            logger.warning(
                f"Attempted to put event {event_id} into finished broker for run {self.run_id}"
            )
            return

        await self.queue.put((event_id, payload))

        # Check if this is an end event
        if isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end":
            self.mark_finished()

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        """Async iterator yielding (event_id, payload) pairs"""
        while True:
            try:
                # Use timeout to check if run is finished
                event_id, payload = await asyncio.wait_for(
                    self.queue.get(), timeout=0.1
                )
                yield event_id, payload

                # Check if this is an end event
                if (
                    isinstance(payload, tuple)
                    and len(payload) >= 1
                    and payload[0] == "end"
                ):
                    break

            except TimeoutError:
                # Check if run is finished and queue is empty
                if self.finished.is_set() and self.queue.empty():
                    break
                continue

    def mark_finished(self) -> None:
        """Mark this broker as finished"""
        self.finished.set()
        logger.debug(f"Broker for run {self.run_id} marked as finished")

    def is_finished(self) -> bool:
        """Check if this broker is finished"""
        return self.finished.is_set()

    def is_empty(self) -> bool:
        """Check if the queue is empty"""
        return self.queue.empty()

    def get_age(self) -> float:
        """Get the age of this broker in seconds"""
        return asyncio.get_event_loop().time() - self._created_at


class BrokerManager(BaseBrokerManager):
    """Manages multiple RunBroker instances"""

    def __init__(self) -> None:
        self._brokers: dict[str, RunBroker] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get_or_create_broker(self, run_id: str) -> RunBroker:
        """Get or create a broker for a run"""
        if run_id not in self._brokers:
            self._brokers[run_id] = RunBroker(run_id)
            logger.debug(f"Created new broker for run {run_id}")
        return self._brokers[run_id]

    def get_broker(self, run_id: str) -> RunBroker | None:
        """Get an existing broker or None"""
        return self._brokers.get(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        """Clean up a broker for a run"""
        if run_id in self._brokers:
            self._brokers[run_id].mark_finished()
            # Don't immediately delete in case there are still consumers
            logger.debug(f"Marked broker for run {run_id} for cleanup")

    def remove_broker(self, run_id: str) -> None:
        """Remove a broker completely"""
        if run_id in self._brokers:
            self._brokers[run_id].mark_finished()
            del self._brokers[run_id]
            logger.debug(f"Removed broker for run {run_id}")

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for old brokers"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_old_brokers())

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    async def _cleanup_old_brokers(self) -> None:
        """Background task to clean up old finished brokers"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                asyncio.get_event_loop().time()
                to_remove = []

                for run_id, broker in self._brokers.items():
                    # Remove brokers that are finished and older than 1 hour
                    if (
                        broker.is_finished()
                        and broker.is_empty()
                        and broker.get_age() > 3600
                    ):
                        to_remove.append(run_id)

                for run_id in to_remove:
                    self.remove_broker(run_id)
                    logger.info(f"Cleaned up old broker for run {run_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broker cleanup task: {e}")


# Global broker manager instance
broker_manager = BrokerManager()
