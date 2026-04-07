"""Unit tests for the Prometheus metrics setup module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from aegra_api.observability.metrics import setup_prometheus_metrics


class TestSetupPrometheusMetrics:
    """Tests for the setup_prometheus_metrics function."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return FastAPI()

    def test_noop_when_disabled(self, app: FastAPI) -> None:
        """Test that no instrumentation is attached when metrics are disabled."""
        with patch("aegra_api.observability.metrics.settings") as mock_settings:
            mock_settings.observability.ENABLE_PROMETHEUS_METRICS = False

            setup_prometheus_metrics(app)

        # No /metrics route should exist
        paths = {route.path for route in app.routes if hasattr(route, "path")}
        assert "/metrics" not in paths

    def test_exposes_metrics_endpoint_when_enabled(self, app: FastAPI) -> None:
        """Test that /metrics endpoint is added when metrics are enabled."""
        with patch("aegra_api.observability.metrics.settings") as mock_settings:
            mock_settings.observability.ENABLE_PROMETHEUS_METRICS = True

            setup_prometheus_metrics(app)

        paths = {route.path for route in app.routes if hasattr(route, "path")}
        assert "/metrics" in paths

    def test_excludes_health_and_docs(self, app: FastAPI) -> None:
        """Test that the instrumentator excludes health and docs endpoints."""
        with (
            patch("aegra_api.observability.metrics.settings") as mock_settings,
            patch("aegra_api.observability.metrics.Instrumentator") as mock_cls,
        ):
            mock_settings.observability.ENABLE_PROMETHEUS_METRICS = True
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.instrument.return_value = mock_instance

            setup_prometheus_metrics(app)

            mock_cls.assert_called_once_with(
                should_group_status_codes=False,
                should_ignore_untemplated=True,
                excluded_handlers=[
                    "/health",
                    "/ready",
                    "/live",
                    "/info",
                    "/metrics",
                    "/docs",
                    "/redoc",
                    "/openapi.json",
                ],
            )
            mock_instance.instrument.assert_called_once_with(app)
            mock_instance.expose.assert_called_once_with(
                app,
                endpoint="/metrics",
                include_in_schema=False,
            )

    def test_logs_when_enabled(self, app: FastAPI) -> None:
        """Test that a log message is emitted when metrics are enabled."""
        with (
            patch("aegra_api.observability.metrics.settings") as mock_settings,
            patch("aegra_api.observability.metrics.logger") as mock_logger,
        ):
            mock_settings.observability.ENABLE_PROMETHEUS_METRICS = True

            setup_prometheus_metrics(app)

            mock_logger.info.assert_called_once_with("Prometheus metrics enabled at /metrics")
