"""Tests for application lifespan and startup logic"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent_server.observability.base import get_observability_manager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifespan_registers_langfuse_provider(monkeypatch):
    """Test that the lifespan function registers the Langfuse provider during startup."""
    # Enable Langfuse so the provider will be registered
    monkeypatch.setenv("LANGFUSE_LOGGING", "true")

    # Reload the module to pick up the env var change
    import src.agent_server.observability.langfuse_integration as langfuse_module

    importlib.reload(langfuse_module)
    # Reload main module to get the updated provider
    import src.agent_server.main as main_module
    from src.agent_server.observability.langfuse_integration import (
        LangfuseProvider,
    )

    importlib.reload(main_module)
    from src.agent_server.main import lifespan

    # Mock all the dependencies that lifespan needs
    with (
        patch("src.agent_server.main.db_manager") as mock_db_manager,
        patch(
            "src.agent_server.main.get_langgraph_service"
        ) as mock_get_langgraph_service,
        patch("src.agent_server.main.event_store") as mock_event_store,
    ):
        # Setup mocks
        mock_db_manager.initialize = AsyncMock()
        mock_db_manager.close = AsyncMock()

        mock_langgraph_service = MagicMock()
        mock_langgraph_service.initialize = AsyncMock()
        mock_get_langgraph_service.return_value = mock_langgraph_service

        mock_event_store.start_cleanup_task = AsyncMock()
        mock_event_store.stop_cleanup_task = AsyncMock()

        # Clear the observability manager before test
        manager = get_observability_manager()
        manager._providers.clear()

        # Create a mock FastAPI app
        mock_app = MagicMock()

        # Run the lifespan function
        async with lifespan(mock_app):
            # Verify that a LangfuseProvider instance is registered
            # Check by type since reloading creates a new instance
            langfuse_providers = [
                p for p in manager._providers if isinstance(p, LangfuseProvider)
            ]
            assert len(langfuse_providers) == 1, (
                "Langfuse provider should be registered during lifespan startup"
            )

            # Verify the observability manager can get callbacks from registered provider
            callbacks = manager.get_all_callbacks()
            # If Langfuse is enabled, we'd get callbacks; if disabled, empty list
            # Either way, the provider should be registered
            assert isinstance(callbacks, list)

        # Verify cleanup was called
        mock_db_manager.close.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifespan_calls_required_initialization():
    """Test that lifespan calls all required initialization functions."""
    from src.agent_server.main import lifespan

    with (
        patch("src.agent_server.main.db_manager") as mock_db_manager,
        patch(
            "src.agent_server.main.get_langgraph_service"
        ) as mock_get_langgraph_service,
        patch("src.agent_server.main.event_store") as mock_event_store,
        patch(
            "src.agent_server.main.get_observability_manager"
        ) as mock_get_observability_manager,
    ):
        # Setup mocks
        mock_db_manager.initialize = AsyncMock()
        mock_db_manager.close = AsyncMock()

        mock_langgraph_service = MagicMock()
        mock_langgraph_service.initialize = AsyncMock()
        mock_get_langgraph_service.return_value = mock_langgraph_service

        mock_event_store.start_cleanup_task = AsyncMock()
        mock_event_store.stop_cleanup_task = AsyncMock()

        mock_manager = MagicMock()
        mock_get_observability_manager.return_value = mock_manager

        mock_app = MagicMock()

        # Run the lifespan function
        async with lifespan(mock_app):
            pass

        # Verify all initialization functions were called
        mock_db_manager.initialize.assert_called_once()
        mock_langgraph_service.initialize.assert_called_once()
        mock_event_store.start_cleanup_task.assert_called_once()

        # Verify observability manager was used to register provider
        mock_get_observability_manager.assert_called()
        # Check that register_provider was called with a LangfuseProvider instance
        assert mock_manager.register_provider.called, (
            "register_provider should be called"
        )
        call_args = mock_manager.register_provider.call_args
        assert call_args is not None
        # Verify it was called with a LangfuseProvider (check by type/class name)
        from src.agent_server.observability.langfuse_integration import LangfuseProvider

        assert isinstance(call_args[0][0], LangfuseProvider), (
            "register_provider should be called with LangfuseProvider instance"
        )

        # Verify cleanup
        mock_event_store.stop_cleanup_task.assert_called_once()
        mock_db_manager.close.assert_called_once()
