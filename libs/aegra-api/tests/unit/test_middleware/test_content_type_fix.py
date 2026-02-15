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
async def test_passes_through_non_http() -> None:
    """Non-HTTP scopes (e.g. websocket) are forwarded unchanged."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {"type": "websocket"}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_passes_through_get_requests() -> None:
    """GET requests are forwarded unchanged regardless of Content-Type."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "GET",
        "headers": [(b"content-type", b"text/plain")],
    }
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)
    assert _get_content_type(scope) == b"text/plain"


@pytest.mark.asyncio
async def test_passes_through_delete_requests() -> None:
    """DELETE requests are forwarded unchanged."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "DELETE",
        "headers": [(b"content-type", b"text/plain")],
    }
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)
    assert _get_content_type(scope) == b"text/plain"


@pytest.mark.asyncio
async def test_rewrites_text_plain_to_json_for_post() -> None:
    """POST with text/plain Content-Type is rewritten to application/json."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_text_plain_charset_utf8() -> None:
    """POST with text/plain;charset=UTF-8 is rewritten to application/json."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain;charset=UTF-8")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_text_plain_charset_with_space() -> None:
    """POST with 'text/plain; charset=utf-8' (with space) is also rewritten."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_for_put_requests() -> None:
    """PUT with text/plain is rewritten to application/json."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "PUT",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_rewrites_for_patch_requests() -> None:
    """PATCH with text/plain is rewritten to application/json."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "PATCH",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_preserves_application_json() -> None:
    """POST with application/json Content-Type is not modified."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"application/json"


@pytest.mark.asyncio
async def test_preserves_multipart_form_data() -> None:
    """POST with multipart/form-data is not modified."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"multipart/form-data; boundary=----abc")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) == b"multipart/form-data; boundary=----abc"


@pytest.mark.asyncio
async def test_no_content_type_header() -> None:
    """POST with no Content-Type header passes through unchanged."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", b"Bearer token")],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    assert _get_content_type(scope) is None
    assert app.called


@pytest.mark.asyncio
async def test_preserves_other_headers() -> None:
    """Middleware only modifies content-type, other headers stay intact."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"authorization", b"Bearer token"),
            (b"content-type", b"text/plain"),
            (b"x-request-id", b"abc-123"),
        ],
    }

    await middleware(scope, AsyncMock(), AsyncMock())

    headers = dict(scope["headers"])
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"authorization"] == b"Bearer token"
    assert headers[b"x-request-id"] == b"abc-123"


@pytest.mark.asyncio
async def test_does_not_touch_receive_or_send() -> None:
    """Middleware never wraps or modifies receive/send callables."""
    app = AsyncMock()
    middleware = ContentTypeFixMiddleware(app)

    receive = AsyncMock()
    send = AsyncMock()
    scope: dict = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    await middleware(scope, receive, send)

    # The original receive and send should be passed through directly
    app.assert_called_once_with(scope, receive, send)
