from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter

from aegra_api.observability.targets.base import BaseOtelTarget
from aegra_api.settings import settings


class PhoenixTarget(BaseOtelTarget):
    @property
    def name(self) -> str:
        return "Phoenix"

    def get_exporter(self) -> SpanExporter | None:
        conf = settings.observability
        endpoint = conf.PHOENIX_COLLECTOR_ENDPOINT

        if not endpoint:
            return None

        headers = {}
        if conf.PHOENIX_API_KEY:
            headers["authorization"] = f"Bearer {conf.PHOENIX_API_KEY}"

        return OTLPSpanExporter(endpoint=endpoint, headers=headers)
