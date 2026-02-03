from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter

from src.agent_server.observability.targets.base import BaseOtelTarget
from src.agent_server.settings import settings


class PhoenixTarget(BaseOtelTarget):
    @property
    def name(self) -> str:
        return "Phoenix"

    def get_exporter(self) -> SpanExporter | None:
        conf = settings.observability
        endpoint = conf.PHOENIX_COLLECTOR_ENDPOINT

        headers = {}
        if conf.PHOENIX_API_KEY:
            headers["api_key"] = conf.PHOENIX_API_KEY

        return OTLPSpanExporter(endpoint=endpoint, headers=headers)
