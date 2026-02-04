from abc import ABC, abstractmethod

from opentelemetry.sdk.trace.export import SpanExporter


class BaseOtelTarget(ABC):
    """Interface for an observability destination."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Friendly name for logging (e.g. 'Langfuse')."""
        pass

    @abstractmethod
    def get_exporter(self) -> SpanExporter | None:
        """Returns a configured exporter or None if config is missing."""
        pass
