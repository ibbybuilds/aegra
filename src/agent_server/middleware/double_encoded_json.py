"""Middleware to handle double-encoded JSON payloads from frontend.

Some frontend clients may send JSON that's been stringified twice,
resulting in payloads like '"{\\"key\\":\\"value\\"}"' instead of '{"key":"value"}'.
This middleware detects and corrects such cases.
"""

import json

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.getLogger(__name__)

# Skip processing for payloads larger than this (likely contain base64 images)
MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB


class DoubleEncodedJSONMiddleware:
    """Detects and unwraps double-encoded JSON payloads."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        # Only process requests that might have JSON bodies
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        # Check content type
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode(
            "latin1", errors="ignore"
        )

        # Only process JSON-like content types (or text/plain which might be mislabeled JSON)
        # But generally we want to be permissive here if we are fixing broken clients
        if (
            "json" not in content_type.lower()
            and "text/plain" not in content_type.lower()
        ):
            # If it's not JSON or Text, it's probably not double-encoded JSON string
            await self.app(scope, receive, send)
            return

        # Buffer the entire request body
        body_chunks: list[bytes] = []
        body_received = False
        total_size = 0

        async def buffering_receive() -> Message:
            nonlocal body_received, total_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if chunk:
                    body_chunks.append(chunk)
                    total_size += len(chunk)

                # Check if this is the last chunk
                if not message.get("more_body", False):
                    body_received = True

            return message

        # Consume the body by calling receive until we have it all or hit the limit
        while not body_received:
            msg = await buffering_receive()
            if msg["type"] == "http.disconnect":
                # Client disconnected
                await self.app(scope, receive, send)  # Pass the disconnect through?
                # Actually, standard is to likely just return?
                # But let's just break and let the app handle it via our wrapped receive
                break

            if total_size > MAX_BODY_SIZE:
                # Too big, stop buffering and pass through what we have + the rest
                logger.debug(
                    f"Payload too large ({total_size}+ bytes), skipping double-encoding check"
                )

                # We need to construct a receive callable that returns:
                # 1. The chunks we already buffered
                # 2. The rest of the stream (which we need to fetch from original receive)

                chunks_to_send = list(body_chunks)  # copy

                async def streaming_receive(
                    chunks: list[bytes] = chunks_to_send,
                ) -> Message:
                    if chunks:
                        chunk = chunks.pop(0)

                        # Determine if there is more body after this chunk
                        has_more_in_buffer = bool(chunks)

                        # If more in buffer, explicitly True.
                        # If buffer empty, it depends on whether we had already received the full body from upstream.
                        # If body_received is True, then this is the final chunk -> False.
                        # If body_received is False, then upstream has more -> True.
                        more_body = has_more_in_buffer or not body_received

                        return {
                            "type": "http.request",
                            "body": chunk,
                            "more_body": more_body,
                        }

                    # If we are here, buffer is empty.
                    # If body_received was True, we theoretically shouldn't reach here if logic above is correct,
                    # or receive() might return disconnect. But we should just delegate safely.
                    return await receive()

                await self.app(scope, streaming_receive, send)
                return

        if not body_received:
            # We must have gotten a disconnect or something odd, just bail
            return

        # Now we have the complete body
        complete_body = b"".join(body_chunks)

        # Process the body
        processed_body = self._process_body(complete_body, total_size, headers, scope)

        # Create a new receive function that returns our processed body
        body_sent = False

        async def body_receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": processed_body,
                    "more_body": False,
                }
            # After body is sent, next call usually expects disconnect or empty/more_body=False
            # But the app loop typically ends when more_body=False.
            # If it calls again, let's just return disconnect to be safe/standard conformant.
            return {"type": "http.disconnect"}

        await self.app(scope, body_receive, send)

    def _process_body(
        self, body: bytes, size: int, headers: dict, scope: Scope
    ) -> bytes:
        """Process the body, unwrapping double-encoded JSON if detected.

        Args:
            body: The complete request body
            size: Size of the body in bytes
            headers: Request headers (for updating Content-Type)
            scope: ASGI scope

        Returns:
            Processed body (unwrapped if double-encoded, original otherwise)
        """
        # Empty body - nothing to process
        if not body:
            return body

        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            # Not valid UTF-8, pass through
            return body

        # Quick heuristic: double-encoded JSON starts with a quote character
        stripped = decoded.strip()
        if not stripped.startswith('"'):
            return body

        # Might be double-encoded, try to parse
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError:
            return body

        # Check if the result is a string (which would indicate double-encoding)
        if not isinstance(parsed, str):
            # It's valid JSON but not a string - e.g. normal JSON object/list
            return body

        # It's a string - check if that string is valid JSON (the inner payload)
        try:
            inner = json.loads(parsed)
            # Successfully parsed inner JSON - this was double-encoded

            # Re-serialize to ensure clean JSON
            result = json.dumps(inner, ensure_ascii=False).encode("utf-8")

            logger.debug(
                f"Unwrapped double-encoded JSON payload ({size} -> {len(result)} bytes)"
            )

            # Fix content type if it was text/plain
            content_type = headers.get(b"content-type", b"").decode(
                "latin1", errors="ignore"
            )
            if "application/json" not in content_type:
                new_headers = []
                for name, value in scope.get("headers", []):
                    if name.lower() != b"content-type":
                        new_headers.append((name, value))
                new_headers.append((b"content-type", b"application/json"))
                scope["headers"] = new_headers

            return result

        except json.JSONDecodeError:
            # The inner string is not JSON - it's just a string value, not double-encoded
            return body
