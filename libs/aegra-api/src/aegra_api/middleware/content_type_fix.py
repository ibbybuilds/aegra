"""Middleware to fix Content-Type for JSON payloads.

Some clients (notably LangGraph Studio) send valid JSON with
Content-Type: text/plain instead of application/json. FastAPI rejects
these with 422 because it won't parse a text/plain body as JSON.

This middleware rewrites the Content-Type header to application/json
when the request looks like a JSON payload. It does NOT buffer or
re-parse the body, so it's safe for large payloads and streaming.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

# Content types that likely contain JSON but aren't labeled correctly.
_TEXT_CONTENT_TYPES = (
    b"text/plain",
    b"text/plain;charset=utf-8",
    b"text/plain;charset=UTF-8",
    b"text/plain; charset=utf-8",
    b"text/plain; charset=UTF-8",
)

_METHODS_WITH_BODY = {b"POST", b"PUT", b"PATCH"}


class ContentTypeFixMiddleware:
    """Rewrite text/plain Content-Type to application/json for mutation requests.

    This is a zero-copy ASGI middleware — it only touches the scope headers,
    never buffers or modifies the request body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method_raw = scope.get("method", "")
        method: bytes = method_raw.encode() if isinstance(method_raw, str) else method_raw or b""
        if method not in _METHODS_WITH_BODY:
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        new_headers = None

        for i, (name, value) in enumerate(headers):
            if name == b"content-type" and value.lower() in _TEXT_CONTENT_TYPES:
                new_headers = list(headers)
                new_headers[i] = (b"content-type", b"application/json")
                break

        if new_headers is not None:
            scope["headers"] = new_headers

        await self.app(scope, receive, send)
