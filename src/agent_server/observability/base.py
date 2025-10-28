"""Base observability interface for extensible tracing and monitoring."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ObservabilityProvider(ABC):
    """Abstract base class for observability providers."""

    @abstractmethod
    def get_callbacks(self) -> list[Any]:
        """Return a list of callbacks for this provider."""
        pass

    @abstractmethod
    def get_metadata(
        self, run_id: str, thread_id: str, user_identity: str | None = None
    ) -> dict[str, Any]:
        """Return metadata to be added to the run configuration."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this provider is enabled."""
        pass


class ObservabilityManager:
    """Manages multiple observability providers."""

    def __init__(self) -> None:
        self._providers: list[ObservabilityProvider] = []

    def register_provider(self, provider: ObservabilityProvider) -> None:
        """Register an observability provider (idempotent for same instance).

        Only registers enabled providers. Skips if the exact same instance
        is already registered (checked by object identity).
        """
        if not provider.is_enabled():
            return

        # Check if this exact instance is already registered (by object identity)
        if provider in self._providers:
            return

        self._providers.append(provider)

    def get_all_callbacks(self) -> list[Any]:
        """Get callbacks from all enabled providers."""
        callbacks = []
        for provider in self._providers:
            try:
                callbacks.extend(provider.get_callbacks())
            except Exception as e:
                logger.error(
                    f"Failed to get callbacks from {provider.__class__.__name__}: {e}"
                )
        return callbacks

    def get_all_metadata(
        self, run_id: str, thread_id: str, user_identity: str | None = None
    ) -> dict[str, Any]:
        """Get metadata from all enabled providers."""
        metadata = {}
        for provider in self._providers:
            try:
                provider_metadata = provider.get_metadata(
                    run_id, thread_id, user_identity
                )
                metadata.update(provider_metadata)
            except Exception as e:
                logger.error(
                    f"Failed to get metadata from {provider.__class__.__name__}: {e}"
                )
        return metadata


# Global observability manager instance
_observability_manager = ObservabilityManager()


def get_observability_manager() -> ObservabilityManager:
    """Get the global observability manager."""
    return _observability_manager


def get_tracing_callbacks() -> list[Any]:
    """Get callbacks from all registered observability providers."""
    return _observability_manager.get_all_callbacks()


def get_tracing_metadata(
    run_id: str, thread_id: str, user_identity: str | None = None
) -> dict[str, Any]:
    """Get metadata from all registered observability providers."""
    return _observability_manager.get_all_metadata(run_id, thread_id, user_identity)
