"""Integration tests for the Prometheus /metrics endpoint."""

import contextlib
from unittest.mock import patch

import prometheus_client
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.observability.metrics import setup_prometheus_metrics


@pytest.fixture(autouse=True)
def _reset_prometheus_registry() -> None:
    """Reset the default Prometheus registry between tests.

    prometheus-fastapi-instrumentator registers collectors on the default
    global registry. Without a reset, the second test that calls
    ``setup_prometheus_metrics`` raises ``ValueError: Duplicated ...``.
    """
    collectors = list(prometheus_client.REGISTRY._names_to_collectors.values())
    for collector in collectors:
        with contextlib.suppress(Exception):
            prometheus_client.REGISTRY.unregister(collector)


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with Prometheus metrics enabled."""
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"msg": "world"}

    with patch("aegra_api.observability.metrics.settings") as mock_settings:
        mock_settings.observability.ENABLE_PROMETHEUS_METRICS = True
        setup_prometheus_metrics(app)

    return app


def test_metrics_endpoint_returns_prometheus_format() -> None:
    """Test that /metrics returns text in Prometheus exposition format."""
    app = _make_app()
    client = TestClient(app)

    # Make a request so there's something to report
    response = client.get("/hello")
    assert response.status_code == 200

    # Scrape metrics
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "text/plain" in metrics_response.headers["content-type"]

    body = metrics_response.text
    # Should contain standard HTTP metrics from the instrumentator
    assert "http_request_duration" in body or "http_requests" in body


def test_metrics_endpoint_not_exposed_when_disabled() -> None:
    """Test that /metrics is not available when metrics are disabled."""
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"msg": "world"}

    with patch("aegra_api.observability.metrics.settings") as mock_settings:
        mock_settings.observability.ENABLE_PROMETHEUS_METRICS = False
        setup_prometheus_metrics(app)

    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 404
