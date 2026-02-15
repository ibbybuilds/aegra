"""Unit tests for ContentTypeFixMiddleware

These tests verify the middleware rewrites text/plain Content-Type headers
to application/json for mutation requests (POST/PUT/PATCH), without
touching the request body.
"""

from unittest.mock import AsyncMock

import pytest

from aegra_api.middleware.content_type_fix import ContentTypeFixMiddleware


def _get_content_type(scope: dict) -> bytes | None:
    """Extract content-type value from scope headers."""
    for name, value in scope.get("headers", []):
        if name == b"content-type":
            return value
    return None


@pytest.mark.asyncio
async def test_passes_through_non_http(
    middleware: ContentTypeFixMiddleware,
    mock_asgi_app: AsyncMock,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """Non-HTTP scopes (e.g. websocket) are forwarded unchanged."""
    scope: dict = {"type": "websocket"}

    await middleware(scope, mock_receive, mock_send)

    mock_asgi_app.assert_called_once_with(scope, mock_receive, mock_send)


@pytest.mark.asyncio
async def test_passes_through_get_requests(
    middleware: ContentTypeFixMiddleware,
    mock_asgi_app: AsyncMock,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """GET requests are forwarded unchanged regardless of Content-Type."""
    scope: dict = {
        "type": "http",
        "method": "GET",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    mock_asgi_app.assert_called_once_with(scope, mock_receive, mock_send)
    assert _get_content_type(scope) == b"text/plain"


@pytest.mark.asyncio
async def test_passes_through_delete_requests(
    middleware: ContentTypeFixMiddleware,
    mock_asgi_app: AsyncMock,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """DELETE requests are forwarded unchanged."""
    scope: dict = {
        "type": "http",
        "method": "DELETE",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    mock_asgi_app.assert_called_once_with(scope, mock_receive, mock_send)
    assert _get_content_type(scope) == b"text/plain"


@pytest.mark.asyncio
async def test_rewrites_text_plain_to_json_for_post(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with text/plain Content-Type is rewritten to application/json."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_text_plain_charset_utf8(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with text/plain;charset=UTF-8 is rewritten to application/json."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain;charset=UTF-8")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_text_plain_charset_with_space(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with 'text/plain; charset=utf-8' (with space) is also rewritten."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_for_put_requests(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """PUT with text/plain is rewritten to application/json."""
    scope: dict = {
        "type": "http",
        "method": "PUT",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_for_patch_requests(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """PATCH with text/plain is rewritten to application/json."""
    scope: dict = {
        "type": "http",
        "method": "PATCH",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_preserves_application_json(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with application/json Content-Type is not modified."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_preserves_multipart_form_data(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with multipart/form-data is not modified."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"multipart/form-data; boundary=----abc")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) == b"multipart/form-data; boundary=----abc"


@pytest.mark.asyncio
async def test_no_content_type_header(
    middleware: ContentTypeFixMiddleware,
    mock_asgi_app: AsyncMock,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """POST with no Content-Type header passes through unchanged."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", b"Bearer token")],
    }

    await middleware(scope, mock_receive, mock_send)

    assert _get_content_type(scope) is None
    assert mock_asgi_app.called


@pytest.mark.asyncio
async def test_preserves_other_headers(
    middleware: ContentTypeFixMiddleware,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """Middleware only modifies content-type, other headers stay intact."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"authorization", b"Bearer token"),
            (b"content-type", b"text/plain"),
            (b"x-request-id", b"abc-123"),
        ],
    }

    await middleware(scope, mock_receive, mock_send)

    headers = dict(scope["headers"])
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"authorization"] == b"Bearer token"
    assert headers[b"x-request-id"] == b"abc-123"


@pytest.mark.asyncio
async def test_does_not_touch_receive_or_send(
    middleware: ContentTypeFixMiddleware,
    mock_asgi_app: AsyncMock,
    mock_receive: AsyncMock,
    mock_send: AsyncMock,
) -> None:
    """Middleware never wraps or modifies receive/send callables."""
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, mock_receive, mock_send)

    # The original receive and send should be passed through directly
    mock_asgi_app.assert_called_once_with(scope, mock_receive, mock_send)
