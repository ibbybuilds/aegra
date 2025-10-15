"""Abstract base classes for the broker system"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class BaseRunBroker(ABC):
    """Abstract base class for a run-specific event broker"""

    @abstractmethod
    async def put(self, event_id: str, payload: Any) -> None:
        """Put an event into the broker queue"""
        pass

    @abstractmethod
    def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        """Async iterator yielding (event_id, payload) pairs"""
        # Abstract async generator method; must be implemented by subclass
        raise NotImplementedError("aiter method must be implemented by subclass")

    @abstractmethod
    def mark_finished(self) -> None:
        """Mark this broker as finished"""
        pass

    @abstractmethod
    def is_finished(self) -> bool:
        """Check if this broker is finished"""
        pass


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
    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for old brokers"""
        pass

    @abstractmethod
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        pass
