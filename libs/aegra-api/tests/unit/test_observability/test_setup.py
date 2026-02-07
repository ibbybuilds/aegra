"""Unit tests for the observability setup module."""

from unittest.mock import MagicMock, patch

import pytest

from aegra_api.observability.setup import setup_observability


class TestSetupObservability:
    """Tests for the setup_observability function."""

    @pytest.fixture
    def mock_deps(self):
        """Patch dependencies used in setup.py."""
        with (
            patch("aegra_api.observability.setup.get_observability_manager") as mock_get_manager,
            patch("aegra_api.observability.setup.otel_provider") as mock_otel_provider,
            patch("aegra_api.observability.setup.logger") as mock_logger,
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager

            yield {
                "manager": mock_manager,
                "provider": mock_otel_provider,
                "logger": mock_logger,
            }

    def test_setup_registers_provider_always(self, mock_deps):
        """Test that the OTEL provider is always registered with the manager."""
        # Arrange: Even if disabled
        mock_deps["provider"].is_enabled.return_value = False

        # Act
        setup_observability()

        # Assert
        mock_deps["manager"].register_provider.assert_called_once_with(mock_deps["provider"])

    def test_setup_initializes_when_enabled(self, mock_deps):
        """Test that setup() is called when the provider is enabled."""
        # Arrange
        mock_deps["provider"].is_enabled.return_value = True

        # Act
        setup_observability()

        # Assert
        mock_deps["provider"].setup.assert_called_once()
        mock_deps["logger"].info.assert_called_with("Observability subsystem initialized successfully.")

    def test_setup_skips_initialization_when_disabled(self, mock_deps):
        """Test that setup() is NOT called when the provider is disabled."""
        # Arrange
        mock_deps["provider"].is_enabled.return_value = False

        # Act
        setup_observability()

        # Assert
        mock_deps["provider"].setup.assert_not_called()
        mock_deps["logger"].info.assert_called_with("Observability is disabled (no targets configured).")

    def test_setup_handles_exceptions_gracefully(self, mock_deps):
        """Test that exceptions during setup are caught and logged."""
        # Arrange
        mock_deps["provider"].is_enabled.return_value = True
        mock_deps["provider"].setup.side_effect = Exception("Connection failed")

        # Act
        setup_observability()

        # Assert
        mock_deps["provider"].setup.assert_called_once()
        # Should log error instead of raising
        mock_deps["logger"].error.assert_called_once()
        assert "Failed to initialize observability" in mock_deps["logger"].error.call_args[0][0]
