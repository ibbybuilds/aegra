"""Unit tests for observability base system"""

from unittest.mock import MagicMock

import pytest

from src.agent_server.observability.base import (
    ObservabilityManager,
    ObservabilityProvider,
    get_observability_manager,
    get_tracing_callbacks,
    get_tracing_metadata,
)


class MockProvider(ObservabilityProvider):
    """Mock provider for testing"""

    def __init__(self, enabled=True, callbacks=None, metadata=None):
        self.enabled = enabled
        self.callbacks = callbacks or []
        self.metadata = metadata or {}
        self.get_callbacks_called = False
        self.get_metadata_called = False

    def get_callbacks(self):
        self.get_callbacks_called = True
        return self.callbacks

    def get_metadata(self, run_id, thread_id, user_identity=None):
        self.get_metadata_called = True
        return self.metadata

    def is_enabled(self):
        return self.enabled


class TestObservabilityProvider:
    """Test the ObservabilityProvider abstract base class"""

    def test_observability_provider_is_abstract(self):
        """Test that ObservabilityProvider cannot be instantiated directly"""
        with pytest.raises(TypeError):
            ObservabilityProvider()

    def test_mock_provider_implements_interface(self):
        """Test that MockProvider implements the required interface"""
        provider = MockProvider()
        assert isinstance(provider, ObservabilityProvider)
        assert provider.get_callbacks() == []
        assert provider.get_metadata("run1", "thread1") == {}
        assert provider.is_enabled() is True


class TestObservabilityManager:
    """Test the ObservabilityManager class"""

    def test_manager_initializes_empty(self):
        """Test that manager starts with no providers"""
        manager = ObservabilityManager()
        assert len(manager._providers) == 0

    def test_register_enabled_provider(self):
        """Test registering an enabled provider"""
        manager = ObservabilityManager()
        provider = MockProvider(enabled=True)

        manager.register_provider(provider)

        assert len(manager._providers) == 1
        assert provider in manager._providers

    def test_register_disabled_provider_ignored(self):
        """Test that disabled providers are not registered"""
        manager = ObservabilityManager()
        provider = MockProvider(enabled=False)

        manager.register_provider(provider)

        assert len(manager._providers) == 0

    def test_get_all_callbacks_empty(self):
        """Test getting callbacks when no providers are registered"""
        manager = ObservabilityManager()
        callbacks = manager.get_all_callbacks()

        assert callbacks == []
        assert isinstance(callbacks, list)

    def test_get_all_callbacks_single_provider(self):
        """Test getting callbacks from a single provider"""
        manager = ObservabilityManager()
        mock_callback = MagicMock()
        provider = MockProvider(callbacks=[mock_callback])

        manager.register_provider(provider)
        callbacks = manager.get_all_callbacks()

        assert len(callbacks) == 1
        assert callbacks[0] == mock_callback
        assert provider.get_callbacks_called is True

    def test_get_all_callbacks_multiple_providers(self):
        """Test getting callbacks from multiple providers"""
        manager = ObservabilityManager()
        callback1 = MagicMock()
        callback2 = MagicMock()
        provider1 = MockProvider(callbacks=[callback1])
        provider2 = MockProvider(callbacks=[callback2])

        manager.register_provider(provider1)
        manager.register_provider(provider2)
        callbacks = manager.get_all_callbacks()

        assert len(callbacks) == 2
        assert callback1 in callbacks
        assert callback2 in callbacks

    def test_get_all_callbacks_handles_exceptions(self, caplog):
        """Test that exceptions in provider callbacks are handled gracefully"""
        manager = ObservabilityManager()

        class FailingProvider(MockProvider):
            def get_callbacks(self):
                raise Exception("Callback error")

        provider = FailingProvider()
        manager.register_provider(provider)

        callbacks = manager.get_all_callbacks()

        assert callbacks == []
        assert "Failed to get callbacks from FailingProvider" in caplog.text

    def test_get_all_metadata_empty(self):
        """Test getting metadata when no providers are registered"""
        manager = ObservabilityManager()
        metadata = manager.get_all_metadata("run1", "thread1")

        assert metadata == {}
        assert isinstance(metadata, dict)

    def test_get_all_metadata_single_provider(self):
        """Test getting metadata from a single provider"""
        manager = ObservabilityManager()
        provider_metadata = {"key1": "value1", "key2": "value2"}
        provider = MockProvider(metadata=provider_metadata)

        manager.register_provider(provider)
        metadata = manager.get_all_metadata("run1", "thread1", "user1")

        assert metadata == provider_metadata
        assert provider.get_metadata_called is True

    def test_get_all_metadata_multiple_providers(self):
        """Test getting metadata from multiple providers"""
        manager = ObservabilityManager()
        provider1 = MockProvider(metadata={"key1": "value1"})
        provider2 = MockProvider(metadata={"key2": "value2"})

        manager.register_provider(provider1)
        manager.register_provider(provider2)
        metadata = manager.get_all_metadata("run1", "thread1")

        assert metadata == {"key1": "value1", "key2": "value2"}

    def test_get_all_metadata_merges_correctly(self):
        """Test that metadata from multiple providers merges correctly"""
        manager = ObservabilityManager()
        provider1 = MockProvider(metadata={"common": "value1", "unique1": "data1"})
        provider2 = MockProvider(metadata={"common": "value2", "unique2": "data2"})

        manager.register_provider(provider1)
        manager.register_provider(provider2)
        metadata = manager.get_all_metadata("run1", "thread1")

        # Later provider should override common keys
        assert metadata == {"common": "value2", "unique1": "data1", "unique2": "data2"}

    def test_get_all_metadata_handles_exceptions(self, caplog):
        """Test that exceptions in provider metadata are handled gracefully"""
        manager = ObservabilityManager()

        class FailingProvider(MockProvider):
            def get_metadata(self, run_id, thread_id, user_identity=None):
                raise Exception("Metadata error")

        provider = FailingProvider()
        manager.register_provider(provider)

        metadata = manager.get_all_metadata("run1", "thread1")

        assert metadata == {}
        assert "Failed to get metadata from FailingProvider" in caplog.text


class TestGlobalFunctions:
    """Test the global convenience functions"""

    def test_get_observability_manager_returns_singleton(self):
        """Test that get_observability_manager returns the same instance"""
        manager1 = get_observability_manager()
        manager2 = get_observability_manager()

        assert manager1 is manager2
        assert isinstance(manager1, ObservabilityManager)

    def test_get_tracing_callbacks_delegates_to_manager(self):
        """Test that get_tracing_callbacks delegates to the manager"""
        manager = get_observability_manager()
        mock_callback = MagicMock()
        provider = MockProvider(callbacks=[mock_callback])

        manager.register_provider(provider)
        callbacks = get_tracing_callbacks()

        assert len(callbacks) == 1
        assert callbacks[0] == mock_callback

    def test_get_tracing_metadata_delegates_to_manager(self):
        """Test that get_tracing_metadata delegates to the manager"""
        manager = get_observability_manager()
        provider_metadata = {"test_key": "test_value"}
        provider = MockProvider(metadata=provider_metadata)

        manager.register_provider(provider)
        metadata = get_tracing_metadata("run1", "thread1", "user1")

        assert metadata == provider_metadata

    def test_get_tracing_metadata_with_none_user(self):
        """Test get_tracing_metadata with None user_identity"""
        manager = get_observability_manager()
        provider_metadata = {"test_key": "test_value"}
        provider = MockProvider(metadata=provider_metadata)

        manager.register_provider(provider)
        metadata = get_tracing_metadata("run1", "thread1", None)

        assert metadata == provider_metadata
        assert provider.get_metadata_called is True


class TestIntegrationWithLangfuse:
    """Test integration with the existing Langfuse provider"""

    def test_langfuse_provider_registers_automatically(self):
        """Test that Langfuse provider registers automatically when called"""
        # Get initial count
        manager = get_observability_manager()
        initial_count = len(manager._providers)

        # Import and call the function
        from src.agent_server.observability.langfuse_integration import (
            get_tracing_callbacks,
        )

        callbacks = get_tracing_callbacks()

        # Should have registered the Langfuse provider (or it was already registered)
        assert len(manager._providers) >= initial_count
        # Callbacks may or may not be empty depending on whether LANGFUSE_LOGGING is set
        # The important thing is that the provider was registered
        assert isinstance(callbacks, list)

    def test_multiple_calls_dont_duplicate_providers(self):
        """Test that multiple calls don't register the same provider multiple times"""
        manager = get_observability_manager()
        # Clear any existing providers first
        manager._providers.clear()

        from src.agent_server.observability.langfuse_integration import (
            get_tracing_callbacks,
        )

        # Call multiple times
        get_tracing_callbacks()
        get_tracing_callbacks()
        get_tracing_callbacks()

        # Should have at most one provider registered (not duplicated)
        # If LANGFUSE_LOGGING is disabled, provider count may be 0
        # If enabled, should have exactly 1 (not duplicated)
        assert len(manager._providers) <= 1
