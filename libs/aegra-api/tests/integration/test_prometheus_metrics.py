"""Integration tests for the Prometheus /metrics endpoint."""

import prometheus_client
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.observability import metrics as metrics_module
from aegra_api.observability.metrics import setup_prometheus_metrics


@pytest.fixture
def fresh_registry() -> prometheus_client.CollectorRegistry:
    """Return an isolated Prometheus registry to avoid global state leaks."""
    return prometheus_client.CollectorRegistry()


def _make_app(
    monkeypatch: pytest.MonkeyPatch,
    registry: prometheus_client.CollectorRegistry,
) -> FastAPI:
    """Create a minimal FastAPI app with Prometheus metrics enabled."""
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"msg": "world"}

    monkeypatch.setattr(metrics_module.settings.observability, "ENABLE_PROMETHEUS_METRICS", True)
    setup_prometheus_metrics(app, registry=registry)
    return app


def test_metrics_endpoint_returns_prometheus_format(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: prometheus_client.CollectorRegistry,
) -> None:
    """Test that /metrics returns text in Prometheus exposition format."""
    app = _make_app(monkeypatch, fresh_registry)
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


def test_metrics_endpoint_not_exposed_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that /metrics is not available when metrics are disabled."""
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"msg": "world"}

    monkeypatch.setattr(metrics_module.settings.observability, "ENABLE_PROMETHEUS_METRICS", False)
    setup_prometheus_metrics(app)

    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 404
