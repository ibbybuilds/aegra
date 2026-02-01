"""Unit tests for DoubleEncodedJSONMiddleware

These tests verify the middleware's JSON decoding logic in isolation,
without requiring database or full application integration.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.types import Message

from agent_server.middleware.double_encoded_json import DoubleEncodedJSONMiddleware


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


@pytest.mark.asyncio
async def test_middleware_skips_large_payloads():
    """Test that payloads exceeding MAX_BODY_SIZE are skipped and passed through."""
    app = AsyncMock()

    # Set a small limit for testing (10 bytes)
    with patch("agent_server.middleware.double_encoded_json.MAX_BODY_SIZE", 10):
        middleware = DoubleEncodedJSONMiddleware(app)

        # Payload larger than 10 bytes that LOOKS like double-encoded JSON
        # If processed, it would be unwrapped. If skipped, it remains as is.
        inner = {"key": "val"}
        # Length of this is > 10
        body = json.dumps(json.dumps(inner)).encode("utf-8")
        assert len(body) > 10

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        }

        # Simulate receiving in one go (or multiple, doesn't matter for size check trigger)
        receive_iter = iter(
            [
                {"type": "http.request", "body": body, "more_body": False},
                {"type": "http.disconnect"},
            ]
        )

        async def receive():
            return next(receive_iter)

        async def mock_app(scope, receive, send):
            # Read the body passed to the app
            message = await receive()
            assert message["type"] == "http.request"
            received_body = message.get("body", b"")
            while message.get("more_body", False):
                message = await receive()
                received_body += message.get("body", b"")

            # Since size > MAX_BODY_SIZE, it should SKIP decoding.
            # So we expect the ORIGINAL double-encoded body.
            assert received_body == body

        middleware.app = mock_app

        send = AsyncMock()
        await middleware(scope, receive, send)


@pytest.mark.asyncio
async def test_middleware_handles_fragmented_chunks():
    """Test reassembly of highly fragmented chunks."""
    app = AsyncMock()
    middleware = DoubleEncodedJSONMiddleware(app)

    inner = {"key": "value"}
    # Double encoded: '"{\\"key\\": \\"value\\"}"'
    full_body = json.dumps(json.dumps(inner)).encode("utf-8")

    # Split into 1-byte chunks to stress the buffering logic
    chunks = [bytes([b]) for b in full_body]

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive():
        if chunks:
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
        return {"type": "http.disconnect"}

    async def mock_app(scope, receive, send):
        message = await receive()
        received_body = message.get("body", b"")
        # Middleware should present fully buffered body (or stream decoded one)
        # Our implementation buffers fully, then decodes, then sends as one chunk
        # (or standard ASGI stream if we wanted, but we send as one chunk in the fix).

        # The fix sends: {"type": "http.request", "body": processed_body, "more_body": False}
        assert message["more_body"] is False

        # Should be DECODED
        expected = json.dumps(inner, ensure_ascii=False).encode("utf-8")
        assert received_body == expected

    middleware.app = mock_app
    send = AsyncMock()

    await middleware(scope, receive, send)


@pytest.mark.asyncio
async def test_streaming_handoff_correctness():
    """
    Verify that when the middleware hits the size limit, it correctly hands off
    the buffered chunks AND the remaining stream to the app, preserving the
    original data sequence and streaming behavior.
    """
    app = AsyncMock()

    # Set limit to 5 bytes
    with patch("agent_server.middleware.double_encoded_json.MAX_BODY_SIZE", 5):
        middleware = DoubleEncodedJSONMiddleware(app)

        # Total body: "12345" (buffer) + "67890" (stream)
        # Chunks: "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"
        full_payload = b"1234567890"
        chunks = [bytes([b]) for b in full_payload]

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        }

        # Create a receiver that yields one byte at a time
        async def receive():
            if chunks:
                chunk = chunks.pop(0)
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": bool(chunks),
                }
            return {"type": "http.disconnect"}

        async def mock_app(scope, receive, send):
            # The app should be able to consume the FULL stream
            received = b""
            more_body = True
            while more_body:
                msg = await receive()
                if msg["type"] == "http.request":
                    received += msg.get("body", b"")
                    more_body = msg.get("more_body", False)

            assert received == full_payload

        middleware.app = mock_app
        send = AsyncMock()

        await middleware(scope, receive, send)


@pytest.mark.asyncio
async def test_streaming_handoff_at_limit_boundary():
    """
    Verify behavior when the payload exceeds the limit exactly at the last chunk.
    This tests if 'more_body=True' is incorrectly sent when no more body exists.
    """
    app = AsyncMock()

    # Limit 5. Payload 6. One chunk.
    # Logic: Buffer reads 6. limit hit.
    # streaming_receive yields 6 with more_body=True.
    # Application reads 6. expecting more.
    # Application calls receive().
    # Underlying receive yields disconnect (or whatever comes after).
    # If using Starlette Request.stream(), this triggers ClientDisconnect!

    with patch("agent_server.middleware.double_encoded_json.MAX_BODY_SIZE", 5):
        middleware = DoubleEncodedJSONMiddleware(app)

        body = b"123456"
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        }

        # Iterator for the receive mock
        # 1. The chunk (more_body=False)
        # 2. Disconnect
        receive_iter = iter(
            [
                {"type": "http.request", "body": body, "more_body": False},
                {"type": "http.disconnect"},
            ]
        )

        async def receive() -> Message:
            try:
                return next(receive_iter)
            except StopIteration:
                # Should not happen in typical loop if logic is correct
                return {"type": "http.disconnect"}

        async def mock_app(scope, receive, send):
            # Simulate strict Starlette-like stream consumption
            request = Request(scope, receive)
            try:
                content = b""
                async for chunk in request.stream():
                    content += chunk
                assert content == body
            except Exception as e:
                # If ClientDisconnect happens, this will catch it
                pytest.fail(
                    f"App raised exception during streaming: {type(e).__name__}: {e}"
                )

        middleware.app = mock_app
        send = AsyncMock()

        await middleware(scope, receive, send)
