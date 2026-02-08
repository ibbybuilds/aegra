import base64
import logging

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter

from aegra_api.observability.targets.base import BaseOtelTarget
from aegra_api.settings import settings

logger = logging.getLogger(__name__)


class LangfuseTarget(BaseOtelTarget):
    @property
    def name(self) -> str:
        return "Langfuse"

    def get_exporter(self) -> SpanExporter | None:
        conf = settings.observability
        pk = conf.LANGFUSE_PUBLIC_KEY
        sk = conf.LANGFUSE_SECRET_KEY

        if not pk or not sk:
            logger.debug("Langfuse credentials missing.")
            return None

        base_host = conf.LANGFUSE_BASE_URL.rstrip("/")
        endpoint = f"{base_host}/api/public/otel/v1/traces"

        auth_str = f"{pk}:{sk}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        return OTLPSpanExporter(endpoint=endpoint, headers={"Authorization": f"Basic {auth_b64}"})
