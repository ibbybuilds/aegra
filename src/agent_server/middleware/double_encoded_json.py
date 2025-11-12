import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class DoubleEncodedJSONMiddleware:
    """Middleware to handle double-encoded JSON payloads from frontend.

    Some frontend clients may send JSON that's been stringified twice,
    resulting in payloads like '"{\"key\":\"value\"}"' instead of '{"key":"value"}'.
    This middleware detects and corrects such cases.

    Note: Skips processing for very large payloads (>10MB) to avoid performance issues
    with file uploads containing large base64-encoded content.
    """

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB limit for middleware processing

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin1")
        content_length = headers.get(b"content-length", b"0")

        # Parse content length
        try:
            length = int(content_length.decode("latin1"))
        except (ValueError, AttributeError):
            length = 0

        # Skip middleware for very large requests (file uploads)
        if length > self.MAX_BODY_SIZE:
            logger.debug(f"Skipping middleware for large request ({length} bytes)")
            await self.app(scope, receive, send)
            return

        if method in ["POST", "PUT", "PATCH"] and content_type:
            body_parts = []

            async def receive_wrapper() -> dict:
                message = await receive()
                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))

                    if not message.get("more_body", False):
                        body = b"".join(body_parts)

                        # Skip processing for large payloads (likely file uploads)
                        if body and len(body) <= self.MAX_BODY_SIZE:
                            try:
                                decoded = body.decode("utf-8")

                                # Only try to parse if it looks like JSON
                                if decoded.strip().startswith(("{", "[")):
                                    parsed = json.loads(decoded)

                                    # Only fix if it's double-encoded (parsed as string)
                                    if isinstance(parsed, str):
                                        parsed = json.loads(parsed)
                                        new_body = json.dumps(parsed).encode("utf-8")

                                        if (
                                            b"content-type" in headers
                                            and content_type != "application/json"
                                        ):
                                            new_headers = []
                                            for name, value in scope.get("headers", []):
                                                if name != b"content-type":
                                                    new_headers.append((name, value))
                                            new_headers.append(
                                                (b"content-type", b"application/json")
                                            )
                                            scope["headers"] = new_headers

                                        return {
                                            "type": "http.request",
                                            "body": new_body,
                                            "more_body": False,
                                        }
                            except (
                                json.JSONDecodeError,
                                ValueError,
                                UnicodeDecodeError,
                            ) as e:
                                # Log the error but don't fail the request
                                logger.debug(
                                    f"Could not parse/fix JSON payload: {e}. Passing through unchanged."
                                )

                return message

            await self.app(scope, receive_wrapper, send)
        else:
            await self.app(scope, receive, send)
