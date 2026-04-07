"""Optional Prometheus metrics via prometheus-fastapi-instrumentator.

Controlled by ``ENABLE_PROMETHEUS_METRICS`` env var (default: false).
When enabled, exposes a ``/metrics`` endpoint with standard HTTP and
Python runtime metrics in Prometheus exposition format.
"""

import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from aegra_api.settings import settings

logger = structlog.getLogger(__name__)


def setup_prometheus_metrics(app: FastAPI) -> None:
    """Conditionally attach Prometheus instrumentator to the app.

    No-op when ``ENABLE_PROMETHEUS_METRICS`` is false.
    """
    if not settings.observability.ENABLE_PROMETHEUS_METRICS:
        return

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/live", "/info", "/metrics", "/docs", "/redoc", "/openapi.json"],
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")
