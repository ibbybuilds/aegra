import logging

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter

from aegra_api.observability.targets.base import BaseOtelTarget
from aegra_api.settings import settings

logger = logging.getLogger(__name__)


class GenericOtelTarget(BaseOtelTarget):
    @property
    def name(self) -> str:
        return "GenericOTLP"

    def get_exporter(self) -> SpanExporter | None:
        conf = settings.observability
        if not conf.OTEL_EXPORTER_OTLP_ENDPOINT:
            return None

        return OTLPSpanExporter(
            endpoint=conf.OTEL_EXPORTER_OTLP_ENDPOINT,
            headers=self._parse_headers(conf.OTEL_EXPORTER_OTLP_HEADERS),
        )

    def _parse_headers(self, headers_str: str | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if not headers_str:
            return headers
        try:
            for item in headers_str.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    headers[k.strip()] = v.strip()
        except Exception as e:
            logger.warning(f"Failed to parse OTEL headers: {e}")
        return headers
