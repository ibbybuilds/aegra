"""Unit tests for Model Armor middleware."""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ava_v1.middleware.model_armor import ModelArmorMiddleware
from ava_v1.shared_libraries.model_armor_client import (
    ModelArmorConfigError,
    ModelArmorViolationError,
)


@pytest.fixture
def mock_env_disabled():
    """Mock environment variables with Model Armor disabled."""
    with patch.dict(
        os.environ,
        {
            "MODEL_ARMOR_ENABLED": "false",
            "ENV_MODE": "LOCAL",
        },
        clear=False,
    ):
        yield


@pytest.fixture
def mock_env_enabled():
    """Mock environment variables with Model Armor enabled."""
    with patch.dict(
        os.environ,
        {
            "MODEL_ARMOR_ENABLED": "true",
            "MODEL_ARMOR_PROJECT_ID": "test-project",
            "MODEL_ARMOR_LOCATION": "us-central1",
            "MODEL_ARMOR_TEMPLATE_ID": "test-template",
            "MODEL_ARMOR_SERVICE_ACCOUNT_PATH": "/tmp/test-sa.json",
            "MODEL_ARMOR_TIMEOUT": "5.0",
            "MODEL_ARMOR_LOG_VIOLATIONS": "true",
            "MODEL_ARMOR_FAIL_OPEN": "false",
        },
        clear=False,
    ):
        # Mock service account file existence
        with patch("ava_v1.shared_libraries.model_armor_client.os.path.isfile", return_value=True):
            yield


@pytest.fixture
def mock_model_request():
    """Create a mock ModelRequest with a user message."""
    # Use MagicMock to avoid needing all required parameters
    request = MagicMock(spec=ModelRequest)
    request.messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Book me a hotel in Miami"),
    ]
    request.state = {}
    request.runtime = None
    return request


@pytest.fixture
def mock_model_response():
    """Create a mock ModelResponse with an AI message."""
    return ModelResponse(
        result=[AIMessage(content="I'd be happy to help you book a hotel in Miami!")],
    )


@pytest.fixture
def mock_handler(mock_model_response):
    """Create a mock handler that returns a ModelResponse."""
    handler = AsyncMock()
    handler.return_value = mock_model_response
    return handler


class TestModelArmorMiddlewareDisabled:
    """Tests for middleware when disabled."""

    def test_disabled_middleware_passes_through(
        self, mock_env_disabled, mock_model_request, mock_handler
    ):
        """Verify middleware is no-op when disabled."""
        middleware = ModelArmorMiddleware()
        assert middleware.config["enabled"] is False

    async def test_disabled_middleware_skips_sanitization(
        self, mock_env_disabled, mock_model_request, mock_handler
    ):
        """Verify no API calls when middleware is disabled."""
        middleware = ModelArmorMiddleware()

        with patch(
            "ava_v1.shared_libraries.model_armor_client.sanitize_user_prompt"
        ) as mock_user_check, patch(
            "ava_v1.shared_libraries.model_armor_client.sanitize_model_response"
        ) as mock_response_check:
            result = await middleware.awrap_model_call(
                mock_model_request, mock_handler
            )

            # Should not call sanitization functions
            mock_user_check.assert_not_called()
            mock_response_check.assert_not_called()

            # Should call handler and return its result
            mock_handler.assert_called_once_with(mock_model_request)
            assert result == mock_handler.return_value


class TestModelArmorMiddlewareEnabled:
    """Tests for middleware when enabled."""

    async def test_clean_prompt_passes_sanitization(
        self, mock_env_enabled, mock_model_request, mock_handler
    ):
        """Verify normal flow with clean content."""
        middleware = ModelArmorMiddleware()

        with patch(
            "ava_v1.middleware.model_armor.sanitize_user_prompt",
            new_callable=AsyncMock,
        ) as mock_user_check, patch(
            "ava_v1.middleware.model_armor.sanitize_model_response",
            new_callable=AsyncMock,
        ) as mock_response_check:
            result = await middleware.awrap_model_call(
                mock_model_request, mock_handler
            )

            # Should call both sanitization checks
            mock_user_check.assert_called_once_with("Book me a hotel in Miami")
            mock_response_check.assert_called_once_with(
                "I'd be happy to help you book a hotel in Miami!"
            )

            # Should call handler and return its result
            mock_handler.assert_called_once_with(mock_model_request)
            assert result == mock_handler.return_value

    async def test_user_prompt_violation_blocks_request(
        self, mock_env_enabled, mock_model_request, mock_handler
    ):
        """Verify request is blocked when user prompt violates policy."""
        middleware = ModelArmorMiddleware()

        # Mock user prompt violation
        violation_error = ModelArmorViolationError(
            "Content violates policy",
            filter_results={"blocked": True, "reason": "inappropriate_content"},
        )

        with patch(
            "ava_v1.middleware.model_armor.sanitize_user_prompt",
            new_callable=AsyncMock,
            side_effect=violation_error,
        ):
            result = await middleware.awrap_model_call(
                mock_model_request, mock_handler
            )

            # Should NOT call handler
            mock_handler.assert_not_called()

            # Should return error response
            assert isinstance(result.result[0], AIMessage)
            assert (
                "violates our content policy"
                in result.result[0].content.lower()
            )

    async def test_model_response_violation_blocks_response(
        self, mock_env_enabled, mock_model_request, mock_handler
    ):
        """Verify response is blocked when model output violates policy."""
        middleware = ModelArmorMiddleware()

        # Mock model response violation
        violation_error = ModelArmorViolationError(
            "Content violates policy",
            filter_results={"blocked": True, "reason": "policy_violation"},
        )

        with patch(
            "ava_v1.middleware.model_armor.sanitize_user_prompt",
            new_callable=AsyncMock,
        ) as mock_user_check, patch(
            "ava_v1.middleware.model_armor.sanitize_model_response",
            new_callable=AsyncMock,
            side_effect=violation_error,
        ):
            result = await middleware.awrap_model_call(
                mock_model_request, mock_handler
            )

            # Should call handler (pre-call passed)
            mock_handler.assert_called_once()

            # Should return safe error response
            assert isinstance(result.result[0], AIMessage)
            assert "cannot provide that information" in result.result[0].content.lower()

    async def test_api_error_fail_closed(
        self, mock_env_enabled, mock_model_request, mock_handler
    ):
        """Verify request is blocked when API is unavailable (fail_open=false)."""
        middleware = ModelArmorMiddleware()

        # Mock API error
        api_error = ModelArmorConfigError("API timeout")

        with patch(
            "ava_v1.middleware.model_armor.sanitize_user_prompt",
            new_callable=AsyncMock,
            side_effect=api_error,
        ):
            with pytest.raises(ModelArmorConfigError, match="API timeout"):
                await middleware.awrap_model_call(mock_model_request, mock_handler)

            # Should NOT call handler
            mock_handler.assert_not_called()

    async def test_api_error_fail_open(
        self, mock_env_enabled, mock_model_request, mock_handler
    ):
        """Verify request is allowed when API is unavailable (fail_open=true)."""
        # Override fail_open setting
        with patch.dict(os.environ, {"MODEL_ARMOR_FAIL_OPEN": "true"}):
            middleware = ModelArmorMiddleware()

            with patch(
                "ava_v1.middleware.model_armor.sanitize_user_prompt",
                new_callable=AsyncMock,
            ) as mock_user_check, patch(
                "ava_v1.middleware.model_armor.sanitize_model_response",
                new_callable=AsyncMock,
            ) as mock_response_check:
                # No exception raised - calls pass through
                result = await middleware.awrap_model_call(
                    mock_model_request, mock_handler
                )

                # Should call handler despite API issues (fail-open mode)
                mock_handler.assert_called_once()
                assert result == mock_handler.return_value


class TestMessageExtraction:
    """Tests for message extraction helpers."""

    def test_extract_last_user_message(self, mock_env_disabled):
        """Test extracting last user message from request."""
        middleware = ModelArmorMiddleware()

        request = MagicMock(spec=ModelRequest)
        request.messages = [
            HumanMessage(content="First message"),
            AIMessage(content="Response"),
            HumanMessage(content="Second message"),
        ]

        result = middleware._extract_last_user_message(request)
        assert result == "Second message"

    def test_extract_multimodal_user_message(self, mock_env_disabled):
        """Test extracting text from multimodal user message."""
        middleware = ModelArmorMiddleware()

        request = MagicMock(spec=ModelRequest)
        request.messages = [
            HumanMessage(
                content=[
                    {"type": "text", "text": "Look at this image"},
                    {"type": "image_url", "image_url": "https://example.com/img.jpg"},
                    {"type": "text", "text": "What do you see?"},
                ]
            ),
        ]

        result = middleware._extract_last_user_message(request)
        assert result == "Look at this image What do you see?"

    def test_extract_last_user_message_no_human_message(self, mock_env_disabled):
        """Test extraction when no HumanMessage exists."""
        middleware = ModelArmorMiddleware()

        request = MagicMock(spec=ModelRequest)
        request.messages = [
            SystemMessage(content="System"),
            AIMessage(content="Response"),
        ]

        result = middleware._extract_last_user_message(request)
        assert result is None

    def test_extract_model_response_text(self, mock_env_disabled, mock_model_response):
        """Test extracting model response text."""
        middleware = ModelArmorMiddleware()

        result = middleware._extract_model_response_text(mock_model_response)
        assert result == "I'd be happy to help you book a hotel in Miami!"

    def test_extract_model_response_no_text(self, mock_env_disabled):
        """Test extraction when response has no text content."""
        middleware = ModelArmorMiddleware()

        response = ModelResponse(
            result=[AIMessage(content="")],
        )

        result = middleware._extract_model_response_text(response)
        assert result == ""


class TestConfiguration:
    """Tests for configuration validation."""

    def test_missing_required_config_when_enabled(self):
        """Test that missing config raises error when enabled."""
        with patch.dict(
            os.environ,
            {
                "MODEL_ARMOR_ENABLED": "true",
                "MODEL_ARMOR_PROJECT_ID": "test-project",
                "MODEL_ARMOR_LOCATION": "us-central1",
                "MODEL_ARMOR_TEMPLATE_ID": "",  # Missing template ID
                "MODEL_ARMOR_SERVICE_ACCOUNT_PATH": "/tmp/test-sa.json",
            },
            clear=False,
        ):
            with patch("ava_v1.shared_libraries.model_armor_client.os.path.isfile", return_value=True):
                with pytest.raises(
                    ModelArmorConfigError, match="missing required configuration"
                ):
                    ModelArmorMiddleware()

    def test_invalid_service_account_path(self):
        """Test that non-existent service account file raises error."""
        with patch.dict(
            os.environ,
            {
                "MODEL_ARMOR_ENABLED": "true",
                "MODEL_ARMOR_PROJECT_ID": "test-project",
                "MODEL_ARMOR_LOCATION": "us-central1",
                "MODEL_ARMOR_TEMPLATE_ID": "test-template",
                "MODEL_ARMOR_SERVICE_ACCOUNT_PATH": "/tmp/nonexistent.json",
            },
            clear=False,
        ):
            with patch("ava_v1.shared_libraries.model_armor_client.os.path.isfile", return_value=False):
                with pytest.raises(
                    ModelArmorConfigError, match="service account file not found"
                ):
                    ModelArmorMiddleware()

    def test_auto_enable_in_production(self):
        """Test that middleware auto-enables in PRODUCTION mode."""
        with patch.dict(
            os.environ,
            {
                "MODEL_ARMOR_ENABLED": "",  # Not explicitly set
                "ENV_MODE": "PRODUCTION",
                "MODEL_ARMOR_PROJECT_ID": "test-project",
                "MODEL_ARMOR_LOCATION": "us-central1",
                "MODEL_ARMOR_TEMPLATE_ID": "test-template",
                "MODEL_ARMOR_SERVICE_ACCOUNT_PATH": "/tmp/test-sa.json",
            },
            clear=False,
        ):
            with patch("ava_v1.shared_libraries.model_armor_client.os.path.isfile", return_value=True):
                middleware = ModelArmorMiddleware()
                assert middleware.config["enabled"] is True
