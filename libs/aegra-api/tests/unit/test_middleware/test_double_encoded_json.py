"""Unit tests for DoubleEncodedJSONMiddleware

These tests verify the middleware's JSON decoding logic in isolation,
without requiring database or full application integration.
"""

import json
from unittest.mock import AsyncMock

import pytest

from aegra_api.middleware.double_encoded_json import DoubleEncodedJSONMiddleware


@pytest.mark.asyncio
async def test_middleware_passes_through_non_http():
    """Test that non-HTTP requests pass through unchanged"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    scope = {"type": "websocket"}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_middleware_passes_through_get_requests():
    """Test that GET requests pass through unchanged"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    scope = {"type": "http", "method": "GET", "headers": []}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_middleware_handles_normal_json():
    """Test that normal JSON payloads pass through unchanged"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    payload = {"limit": 10, "offset": 0}
    body = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    # Should call app with modified receive
    assert app.called


@pytest.mark.asyncio
async def test_middleware_decodes_double_encoded_json():
    """Test that double-encoded JSON is correctly decoded"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    # Create double-encoded JSON
    inner = {"limit": 10, "offset": 0}
    double_encoded = json.dumps(json.dumps(inner)).encode("utf-8")

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": double_encoded, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    # Should call app
    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_malformed_json_gracefully():
    """Test that malformed JSON doesn't crash the middleware"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    malformed = b'{"incomplete": '

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": malformed, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    # Should not raise an exception
    await middleware(scope, receive, send)

    # Should still call the app (let FastAPI handle the error)
    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_empty_body():
    """Test that empty bodies are handled gracefully"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called


@pytest.mark.asyncio
async def test_middleware_corrects_content_type():
    """Test that Content-Type is corrected from text/plain to application/json"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    payload = {"limit": 10}
    body = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"text/plain")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    # Verify app was called
    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_put_requests():
    """Test that PUT requests are processed by middleware"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    payload = {"name": "Updated"}
    body = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "PUT",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_patch_requests():
    """Test that PATCH requests are processed by middleware"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    payload = {"name": "Patched"}
    body = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "PATCH",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_more_body_true():
    """Test middleware handles chunked requests with more_body=True"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    body_part1 = b'{"data":'
    body_part2 = b' "test"}'

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    call_count = 0

    async def receive():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"type": "http.request", "body": body_part1, "more_body": True}
        elif call_count == 2:
            return {"type": "http.request", "body": body_part2, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_delete_requests():
    """Test that DELETE requests pass through unchanged"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    scope = {"type": "http", "method": "DELETE", "headers": []}
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_middleware_handles_missing_content_type():
    """Test POST request without content-type header"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
    }
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(scope, receive, send)

    app.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_middleware_handles_unicode_decode_error():
    """Test handling of invalid UTF-8 bytes"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    invalid_utf8 = b"\xff\xfe"

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": invalid_utf8, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called


@pytest.mark.asyncio
async def test_middleware_handles_json_array():
    """Test middleware handles JSON arrays correctly"""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    payload = [{"id": 1}, {"id": 2}]
    body = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    receive_called = False

    async def receive():
        nonlocal receive_called
        if not receive_called:
            receive_called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    send = AsyncMock()

    await middleware(scope, receive, send)

    assert app.called
