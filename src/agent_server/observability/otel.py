import json
from abc import ABC, abstractmethod
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from src.agent_server.config import load_observability_config
from src.agent_server.observability.base import ObservabilityProvider
from src.agent_server.settings import settings

logger = structlog.get_logger(__name__)


class BaseOtelTarget(ABC):
    """Abstract base class for OpenTelemetry export targets."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the target."""
        pass

    @abstractmethod
    def get_exporter(self) -> SpanExporter | None:
        """Return a configured SpanExporter or None if disabled."""
        pass


class GenericOTLPTarget(BaseOtelTarget):
    """Generic OTLP target configured via settings/config."""

    def __init__(self, name: str, endpoint: str, headers: dict[str, str] | None = None):
        self._name = name
        self._endpoint = endpoint
        self._headers = headers

    @property
    def name(self) -> str:
        return self._name

    def get_exporter(self) -> SpanExporter | None:
        return OTLPSpanExporter(
            endpoint=self._endpoint,
            headers=self._headers,
        )


class OpenTelemetryProvider(ObservabilityProvider):
    """
    Pure OpenTelemetry provider that fans out traces to configured targets.

    Configuration sources (merged):
    1. aegra.json "observability" section
    2. OTEL_EXPORTERS environment variable (JSON)
    3. Legacy LANGFUSE_* settings (backward compatibility)
    """

    def __init__(self) -> None:
        self._tracer_provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.app.PROJECT_NAME,
                    "service.version": settings.app.VERSION,
                }
            )
        )
        self._initialized = False

    def is_enabled(self) -> bool:
        # Check if any exporters are configured
        return bool(self._get_configured_targets())

    def _get_configured_targets(self) -> list[BaseOtelTarget]:
        """Aggregate targets from all configuration sources."""
        targets: list[BaseOtelTarget] = []

        # 1. aegra.json config
        obs_config = load_observability_config()
        if obs_config and "exporters" in obs_config:
            for name, cfg in obs_config["exporters"].items():
                targets.append(
                    GenericOTLPTarget(
                        name=name,
                        endpoint=cfg["endpoint"],
                        headers=cfg.get("headers"),
                    )
                )

        # 2. Environment variable OTEL_EXPORTERS (JSON)
        if settings.otel.OTEL_EXPORTERS:
            try:
                env_exporters = json.loads(settings.otel.OTEL_EXPORTERS)
                for name, cfg in env_exporters.items():
                    targets.append(
                        GenericOTLPTarget(
                            name=name,
                            endpoint=cfg["endpoint"],
                            headers=cfg.get("headers"),
                        )
                    )
            except json.JSONDecodeError:
                logger.warning("Failed to parse OTEL_EXPORTERS JSON")

        return targets

    def initialize(self) -> None:
        """Initialize the global trace provider and processors."""
        if self._initialized:
            return

        targets = self._get_configured_targets()

        for target in targets:
            exporter = target.get_exporter()
            if exporter:
                logger.info(f"Adding OTEL exporter: {target.name}")
                self._tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        # Register as global tracer provider
        trace.set_tracer_provider(self._tracer_provider)

        # Auto-instrumentation for LangChain/LangGraph
        try:
            from openinference.instrumentation.langchain import LangChainInstrumentor

            LangChainInstrumentor().instrument(tracer_provider=self._tracer_provider)
        except ImportError:
            pass

        self._initialized = True

    def get_callbacks(self) -> list[Any]:
        """
        Pure OTEL implementation uses global auto-instrumentation, NOT callbacks.
        Returns empty list because we rely on 'openinference' hooking into LangChain globally.
        """
        if not self._initialized and self.is_enabled():
            self.initialize()
        return []

    def get_metadata(
        self, _run_id: str, _thread_id: str, _user_identity: str | None = None
    ) -> dict[str, Any]:
        """
        Return metadata. For OTEL, we might want to attach this context to the active span,
        but typically this method is used by the graph runner to pass config.
        We can return standard metadata if needed, but for now we return generic info.
        """
        return {}


# Singleton instance
_otel_provider = OpenTelemetryProvider()
