"""Unit tests for Langfuse integration"""

import importlib
import logging
import sys
from unittest.mock import MagicMock, patch


def reload_langfuse_module():
    """Helper to reload the langfuse_integration module AND settings safely"""

    # 1. Ensure modules are imported

    # 2. Reload settings via sys.modules to avoid ImportError
    if "src.agent_server.settings" in sys.modules:
        importlib.reload(sys.modules["src.agent_server.settings"])

    # 3. Reload integration module
    if "src.agent_server.observability.langfuse_integration" in sys.modules:
        return importlib.reload(
            sys.modules["src.agent_server.observability.langfuse_integration"]
        )

    # Fallback if somehow not in sys.modules (unlikely now)
    import src.agent_server.observability.langfuse_integration as m

    return importlib.reload(m)


class TestGetTracingCallbacks:
    """Test get_tracing_callbacks function"""

    def test_callbacks_disabled_explicitly(self, monkeypatch):
        """Test that callbacks are disabled when LANGFUSE_LOGGING is explicitly false"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "false")

        langfuse_module = reload_langfuse_module()
        callbacks = langfuse_module.get_tracing_callbacks()

        assert callbacks == []
        assert isinstance(callbacks, list)

    def test_callbacks_disabled_explicitly_false(self, monkeypatch):
        """Test that callbacks are disabled when LANGFUSE_LOGGING is 'false'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "false")

        langfuse_module = reload_langfuse_module()
        callbacks = langfuse_module.get_tracing_callbacks()

        assert callbacks == []

    def test_callbacks_disabled_uppercase_false(self, monkeypatch):
        """Test that callbacks are disabled when LANGFUSE_LOGGING is 'FALSE'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "FALSE")

        langfuse_module = reload_langfuse_module()
        callbacks = langfuse_module.get_tracing_callbacks()

        assert callbacks == []

    def test_callbacks_disabled_with_zero(self, monkeypatch):
        """Test that callbacks are disabled when LANGFUSE_LOGGING is '0'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "0")

        langfuse_module = reload_langfuse_module()
        callbacks = langfuse_module.get_tracing_callbacks()

        assert callbacks == []

    def test_callbacks_enabled_with_true(self, monkeypatch):
        """Test that callbacks are enabled when LANGFUSE_LOGGING is 'true'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert len(callbacks) == 1
            assert callbacks[0] == mock_handler

    def test_callbacks_enabled_uppercase_true(self, monkeypatch):
        """Test that callbacks are enabled when LANGFUSE_LOGGING is 'TRUE'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "TRUE")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert len(callbacks) == 1
            assert callbacks[0] == mock_handler

    def test_callbacks_enabled_mixed_case_true(self, monkeypatch):
        """Test that callbacks are enabled when LANGFUSE_LOGGING is 'True'"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "True")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert len(callbacks) == 1
            assert callbacks[0] == mock_handler

    def test_import_error_when_langfuse_not_installed(self, monkeypatch, caplog):
        """Test handling when langfuse package is not installed"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        with (
            patch.dict("sys.modules", {"langfuse.langchain": None}),
            caplog.at_level(logging.WARNING),
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert callbacks == []
            assert any(
                "LANGFUSE_LOGGING is true, but 'langfuse' is not installed"
                in record.message
                for record in caplog.records
            )

    def test_generic_exception_during_initialization(self, monkeypatch, caplog):
        """Test handling of generic exceptions during handler initialization"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_callback_handler_class = MagicMock(
            side_effect=Exception("Connection error")
        )

        with (
            patch.dict(
                "sys.modules",
                {
                    "langfuse.langchain": MagicMock(
                        CallbackHandler=mock_callback_handler_class
                    )
                },
            ),
            caplog.at_level(logging.ERROR),
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert callbacks == []
            assert any(
                "Failed to initialize Langfuse CallbackHandler" in record.message
                for record in caplog.records
            )
            assert any(
                "Connection error" in record.message for record in caplog.records
            )

    def test_handler_is_stateless(self, monkeypatch):
        """Test that handler is created without state (stateless pattern)"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler_instance = MagicMock()
        mock_handler_class = MagicMock(return_value=mock_handler_instance)

        with patch.dict(
            "sys.modules",
            {"langfuse.langchain": MagicMock(CallbackHandler=mock_handler_class)},
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            mock_handler_class.assert_called_once_with()
            assert callbacks[0] == mock_handler_instance

    def test_logger_info_on_success(self, monkeypatch, caplog):
        """Test that info log is written when handler is successfully created"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with (
            patch.dict(
                "sys.modules",
                {
                    "langfuse.langchain": MagicMock(
                        CallbackHandler=mock_callback_handler_class
                    )
                },
            ),
            caplog.at_level(logging.INFO),
        ):
            langfuse_module = reload_langfuse_module()
            langfuse_module.get_tracing_callbacks()

            assert any(
                "Langfuse tracing enabled, handler created" in record.message
                for record in caplog.records
            )

    def test_multiple_calls_return_same_handlers(self, monkeypatch):
        """Test that multiple calls to get_tracing_callbacks return the same handler instances"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()

            callbacks_1 = langfuse_module.get_tracing_callbacks()
            callbacks_2 = langfuse_module.get_tracing_callbacks()

            assert len(callbacks_1) == 1
            assert len(callbacks_2) == 1
            # With the new system, the same provider instance is reused
            assert callbacks_1[0] == callbacks_2[0]

    def test_callbacks_list_is_mutable(self, monkeypatch):
        """Test that returned callbacks list is mutable and can be extended"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            other_callback = MagicMock()
            callbacks.append(other_callback)

            assert len(callbacks) == 2
            assert callbacks[0] == mock_handler
            assert callbacks[1] == other_callback

    def test_disabled_returns_empty_list_not_none(self, monkeypatch):
        """Test that disabled state returns empty list, not None"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "false")

        langfuse_module = reload_langfuse_module()
        callbacks = langfuse_module.get_tracing_callbacks()

        assert callbacks is not None
        assert callbacks == []
        assert isinstance(callbacks, list)

    def test_import_error_returns_empty_list_not_none(self, monkeypatch):
        """Test that ImportError returns empty list, not None"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        with patch.dict("sys.modules", {"langfuse.langchain": None}):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert callbacks is not None
            assert callbacks == []
            assert isinstance(callbacks, list)

    def test_exception_returns_empty_list_not_none(self, monkeypatch):
        """Test that exceptions return empty list, not None"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_callback_handler_class = MagicMock(side_effect=Exception("Test error"))

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            callbacks = langfuse_module.get_tracing_callbacks()

            assert callbacks is not None
            assert callbacks == []
            assert isinstance(callbacks, list)

    def test_env_var_case_insensitive(self, monkeypatch):
        """Test that environment variable value is case-insensitive"""
        from src.agent_server.observability.base import get_observability_manager

        test_cases = ["true", "True", "TRUE", "TrUe"]

        for value in test_cases:
            # Clear the manager for each iteration since we're reloading the module
            manager = get_observability_manager()
            manager._providers.clear()

            monkeypatch.setenv("LANGFUSE_LOGGING", value)

            mock_handler = MagicMock()
            mock_callback_handler_class = MagicMock(return_value=mock_handler)

            with patch.dict(
                "sys.modules",
                {
                    "langfuse.langchain": MagicMock(
                        CallbackHandler=mock_callback_handler_class
                    )
                },
            ):
                langfuse_module = reload_langfuse_module()
                callbacks = langfuse_module.get_tracing_callbacks()

                assert len(callbacks) == 1, f"Failed for value: {value}"


class TestLangfuseProvider:
    """Test the LangfuseProvider class"""

    def test_langfuse_provider_implements_interface(self, monkeypatch):
        """Test that LangfuseProvider implements the ObservabilityProvider interface"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        from src.agent_server.observability.base import ObservabilityProvider

        assert isinstance(provider, ObservabilityProvider)

    def test_langfuse_provider_enabled_when_env_true(self, monkeypatch):
        """Test that LangfuseProvider is enabled when LANGFUSE_LOGGING is true"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        assert provider.is_enabled() is True

    def test_langfuse_provider_disabled_when_env_false(self, monkeypatch):
        """Test that LangfuseProvider is disabled when LANGFUSE_LOGGING is false"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "false")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        assert provider.is_enabled() is False

    def test_langfuse_provider_get_metadata_with_user(self, monkeypatch):
        """Test that LangfuseProvider returns correct metadata with user"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        metadata = provider.get_metadata("run123", "thread456", "user789")

        expected = {
            "langfuse_session_id": "thread456",
            "langfuse_user_id": "user789",
            "langfuse_tags": [
                "aegra_run",
                "run:run123",
                "thread:thread456",
                "user:user789",
            ],
        }
        assert metadata == expected

    def test_langfuse_provider_get_metadata_without_user(self, monkeypatch):
        """Test that LangfuseProvider returns correct metadata without user"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        metadata = provider.get_metadata("run123", "thread456", None)

        expected = {
            "langfuse_session_id": "thread456",
            "langfuse_tags": [
                "aegra_run",
                "run:run123",
                "thread:thread456",
            ],
        }
        assert metadata == expected

    def test_langfuse_provider_get_callbacks_when_enabled(self, monkeypatch):
        """Test that LangfuseProvider returns callbacks when enabled"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "true")

        mock_handler = MagicMock()
        mock_callback_handler_class = MagicMock(return_value=mock_handler)

        with patch.dict(
            "sys.modules",
            {
                "langfuse.langchain": MagicMock(
                    CallbackHandler=mock_callback_handler_class
                )
            },
        ):
            langfuse_module = reload_langfuse_module()
            provider = langfuse_module.LangfuseProvider()

            callbacks = provider.get_callbacks()

            assert len(callbacks) == 1
            assert callbacks[0] == mock_handler

    def test_langfuse_provider_get_callbacks_when_disabled(self, monkeypatch):
        """Test that LangfuseProvider returns empty callbacks when disabled"""
        monkeypatch.setenv("LANGFUSE_LOGGING", "false")

        langfuse_module = reload_langfuse_module()
        provider = langfuse_module.LangfuseProvider()

        callbacks = provider.get_callbacks()

        assert callbacks == []
