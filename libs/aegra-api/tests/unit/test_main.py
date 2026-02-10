"""Tests for application lifespan and startup logic"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegra_api.observability.base import get_observability_manager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifespan_registers_otel_provider(monkeypatch):
    """Test that the lifespan function registers the OpenTelemetry provider during startup."""
    # Configure OTEL_TARGETS so the provider is enabled
    monkeypatch.setenv("OTEL_TARGETS", "LANGFUSE")

    # 1. Reload settings
    import aegra_api.settings as settings_module

    importlib.reload(settings_module)

    # 2. Reload otel module (creates new Provider class/instance)
    import aegra_api.observability.otel as otel_module

    importlib.reload(otel_module)
    # 3. Reload setup module (crucial! so it imports the NEW otel_provider)
    import aegra_api.observability.setup as setup_module
    from aegra_api.observability.otel import OpenTelemetryProvider

    importlib.reload(setup_module)

    # 4. Reload main module
    import aegra_api.main as main_module

    importlib.reload(main_module)
    from aegra_api.main import lifespan

    # Mock all the dependencies
    with (
        patch("aegra_api.main.run_migrations_async", new_callable=AsyncMock),
        patch("aegra_api.main.db_manager") as mock_db_manager,
        patch("aegra_api.main.get_langgraph_service") as mock_get_langgraph_service,
        patch("aegra_api.main.event_store") as mock_event_store,
    ):
        mock_db_manager.initialize = AsyncMock()
        mock_db_manager.close = AsyncMock()

        mock_langgraph_service = MagicMock()
        mock_langgraph_service.initialize = AsyncMock()
        mock_get_langgraph_service.return_value = mock_langgraph_service

        mock_event_store.start_cleanup_task = AsyncMock()
        mock_event_store.stop_cleanup_task = AsyncMock()

        # Clear the manager
        manager = get_observability_manager()
        manager._providers.clear()

        mock_app = MagicMock()

        async with lifespan(mock_app):
            # Verify OpenTelemetryProvider is registered
            otel_providers = [p for p in manager._providers if isinstance(p, OpenTelemetryProvider)]
            assert len(otel_providers) == 1, "OpenTelemetry provider should be registered during lifespan startup"

        mock_db_manager.close.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifespan_calls_required_initialization():
    """Test that lifespan calls all required initialization functions."""
    # Reload main to ensure clean state
    import aegra_api.main as main_module

    importlib.reload(main_module)
    from aegra_api.main import lifespan

    with (
        patch("aegra_api.main.run_migrations_async", new_callable=AsyncMock) as mock_migrations,
        patch("aegra_api.main.db_manager") as mock_db_manager,
        patch("aegra_api.main.get_langgraph_service") as mock_get_langgraph_service,
        patch("aegra_api.main.event_store") as mock_event_store,
        # Patch the new setup_observability function directly
        patch("aegra_api.main.setup_observability") as mock_setup_observability,
    ):
        # Setup mocks
        mock_db_manager.initialize = AsyncMock()
        mock_db_manager.close = AsyncMock()

        mock_langgraph_service = MagicMock()
        mock_langgraph_service.initialize = AsyncMock()
        mock_get_langgraph_service.return_value = mock_langgraph_service

        mock_event_store.start_cleanup_task = AsyncMock()
        mock_event_store.stop_cleanup_task = AsyncMock()

        mock_app = MagicMock()

        # Run the lifespan function
        async with lifespan(mock_app):
            pass

        # Verify migrations run first, then initialization
        mock_migrations.assert_called_once()
        mock_db_manager.initialize.assert_called_once()
        mock_langgraph_service.initialize.assert_called_once()
        mock_event_store.start_cleanup_task.assert_called_once()

        # Verify observability setup was called
        mock_setup_observability.assert_called_once()

        # Verify cleanup
        mock_event_store.stop_cleanup_task.assert_called_once()
        mock_db_manager.close.assert_called_once()
