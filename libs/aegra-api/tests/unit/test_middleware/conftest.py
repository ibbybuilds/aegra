"""Shared fixtures for middleware unit tests."""

from unittest.mock import AsyncMock

import pytest

from aegra_api.middleware.content_type_fix import ContentTypeFixMiddleware


@pytest.fixture
def mock_asgi_app() -> AsyncMock:
    """Mock ASGI application that the middleware wraps."""
    return AsyncMock()


@pytest.fixture
def middleware(mock_asgi_app: AsyncMock) -> ContentTypeFixMiddleware:
    """ContentTypeFixMiddleware wrapping the mock ASGI app."""
    return ContentTypeFixMiddleware(mock_asgi_app)


@pytest.fixture
def mock_receive() -> AsyncMock:
    """Mock ASGI receive callable."""
    return AsyncMock()


@pytest.fixture
def mock_send() -> AsyncMock:
    """Mock ASGI send callable."""
    return AsyncMock()
