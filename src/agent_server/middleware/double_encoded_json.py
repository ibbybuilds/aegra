import json

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.getLogger(__name__)


class DoubleEncodedJSONMiddleware:
    """Middleware to handle double-encoded JSON payloads from frontend.

    Some frontend clients may send JSON that's been stringified twice,
    resulting in payloads like '"{\"key\":\"value\"}"' instead of '{"key":"value"}'.
    This middleware detects and corrects such cases.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin1")

        if method in ["POST", "PUT", "PATCH"] and content_type:
            body_parts = []

            async def receive_wrapper() -> dict:
                message = await receive()
                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))

                    if not message.get("more_body", False):
                        body = b"".join(body_parts)

                        if body:
                            try:
                                decoded = body.decode("utf-8")
                                parsed = json.loads(decoded)

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
                            ):
                                pass

                return message

            await self.app(scope, receive_wrapper, send)
        else:
            await self.app(scope, receive, send)
