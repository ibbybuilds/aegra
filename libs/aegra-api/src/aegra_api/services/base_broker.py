"""Abstract base classes for the broker system"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class BaseRunBroker(ABC):
    """Abstract base class for a run-specific event broker.

    Handles both live event broadcast and replay storage for SSE reconnection.
    """

    @abstractmethod
    async def put(self, event_id: str, payload: Any, *, resumable: bool = True) -> None:
        """Publish an event to live subscribers and optionally store for replay.

        Args:
            event_id: Unique event identifier (format: {run_id}_event_{seq}).
            payload: The event data (typically a tuple like ("values", {...})).
            resumable: If True, store the event for replay on reconnect.
        """

    @abstractmethod
    def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        """Async iterator yielding (event_id, payload) pairs."""
        ...

    @abstractmethod
    async def replay(self, last_event_id: str | None) -> list[tuple[str, Any]]:
        """Return stored events for replay on reconnect.

        Args:
            last_event_id: If provided, return events after this ID.
                           If None, return all stored events.

        Returns:
            List of (event_id, payload) tuples in order.
        """

    @abstractmethod
    def mark_finished(self) -> None:
        """Mark this broker as finished."""

    @abstractmethod
    def is_finished(self) -> bool:
        """Check if this broker is finished."""


class BaseBrokerManager(ABC):
    """Abstract base class for managing multiple RunBroker instances"""

    @abstractmethod
    def get_or_create_broker(self, run_id: str) -> BaseRunBroker:
        """Get or create a broker for a run"""
        pass

    @abstractmethod
    def get_broker(self, run_id: str) -> BaseRunBroker | None:
        """Get an existing broker or None"""
        pass

    @abstractmethod
    def cleanup_broker(self, run_id: str) -> None:
        """Clean up a broker for a run"""
        pass

    @abstractmethod
    def remove_broker(self, run_id: str) -> None:
        """Remove a broker completely"""
        pass

    @abstractmethod
    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for old brokers"""
        pass

    @abstractmethod
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        pass
