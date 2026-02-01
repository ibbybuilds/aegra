from unittest.mock import patch

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from src.agent_server.observability.otel import (
    GenericOTLPTarget,
    OpenTelemetryProvider,
)


class TestGenericOTLPTarget:
    def test_get_exporter_returns_configured_exporter(self):
        target = GenericOTLPTarget(
            name="test-target",
            endpoint="http://localhost:4318",
            headers={"Authorization": "Bearer token"},
        )
        exporter = target.get_exporter()

        assert isinstance(exporter, OTLPSpanExporter)
        assert exporter._endpoint == "http://localhost:4318"
        assert exporter._headers == {"Authorization": "Bearer token"}


class TestOpenTelemetryProvider:
    @patch("src.agent_server.observability.otel.load_observability_config")
    @patch("src.agent_server.observability.otel.settings")
    def test_provider_initialization_aegra_json(self, mock_settings, mock_load_config):
        # Setup mock settings
        mock_settings.otel.OTEL_EXPORTERS = "{}"

        # Mock aegra.json config
        mock_load_config.return_value = {
            "exporters": {
                "json-target": {
                    "endpoint": "http://json:4318",
                    "headers": {"x-test": "1"},
                }
            }
        }

        provider = OpenTelemetryProvider()
        targets = provider._get_configured_targets()

        assert len(targets) == 1
        assert targets[0].name == "json-target"
        assert targets[0].get_exporter()._endpoint == "http://json:4318"

    @patch(
        "src.agent_server.observability.otel.load_observability_config",
        return_value=None,
    )
    @patch("src.agent_server.observability.otel.settings")
    def test_provider_initialization_env_var(self, mock_settings, mock_load_config):
        mock_settings.otel.OTEL_EXPORTERS = (
            '{"env-target": {"endpoint": "http://env:4318"}}'
        )

        provider = OpenTelemetryProvider()
        targets = provider._get_configured_targets()

        assert len(targets) == 1
        assert targets[0].name == "env-target"
        assert targets[0].get_exporter()._endpoint == "http://env:4318"

    @patch("src.agent_server.observability.otel.load_observability_config")
    @patch("src.agent_server.observability.otel.settings")
    def test_provider_initialization_merged(self, mock_settings, mock_load_config):
        mock_settings.otel.OTEL_EXPORTERS = '{"env-target": {"endpoint": "endpoint2"}}'

        # Test merging sources
        mock_load_config.return_value = {
            "exporters": {"json-target": {"endpoint": "endpoint1"}}
        }

        provider = OpenTelemetryProvider()
        targets = provider._get_configured_targets()

        # Sort by name for stable assertion
        targets.sort(key=lambda x: x.name)

        assert len(targets) == 2
        assert targets[0].name == "env-target"
        assert targets[1].name == "json-target"

    @patch("src.agent_server.observability.otel.load_observability_config")
    def test_is_enabled_new_config(self, mock_load_config):
        # Enabled via new config
        mock_load_config.return_value = {
            "exporters": {"test": {"endpoint": "http://localhost"}}
        }
        provider = OpenTelemetryProvider()
        assert provider.is_enabled() is True

    @patch(
        "src.agent_server.observability.otel.load_observability_config",
        return_value=None,
    )
    @patch("src.agent_server.observability.otel.settings")
    def test_is_enabled_false(self, mock_settings, mock_load_config):
        mock_settings.otel.OTEL_EXPORTERS = "{}"

        provider = OpenTelemetryProvider()
        assert provider.is_enabled() is False
