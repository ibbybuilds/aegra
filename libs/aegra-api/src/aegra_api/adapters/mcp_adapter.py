"""MCP (Model Context Protocol) adapter.

Exposes each graph as an MCP tool via Streamable HTTP at /mcp.
Uses the `mcp` SDK's FastMCP server.

Authentication is handled by ASGI middleware that calls the same auth
backend as the Agent Protocol endpoints. The authenticated user is
stored in a ``ContextVar`` so the tool handler can read it without
access to the HTTP request.
"""

import contextvars
import json
from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import FastAPI
from mcp import types as mcp_types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import MCPTool
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from aegra_api.adapters.mcp_service import MCPService, get_mcp_service
from aegra_api.core.auth_deps import _to_user_model
from aegra_api.core.auth_middleware import get_auth_backend
from aegra_api.models.auth import User

logger = structlog.get_logger(__name__)

# ContextVar to thread the authenticated user from ASGI middleware into
# MCP tool handlers (which don't have access to the HTTP request).
_current_user: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "_current_user", default=None
)


class _AuthMiddleware:
    """ASGI middleware that authenticates requests using Aegra's auth backend.

    Calls the same auth backend configured for Agent Protocol endpoints.
    On success, stores the authenticated ``User`` in a ``ContextVar``
    so downstream MCP tool handlers can access it. On failure, returns
    a 401 JSON response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = StarletteRequest(scope, receive)
        backend = get_auth_backend()

        try:
            result = await backend.authenticate(request)
        except Exception as exc:
            response = StarletteJSONResponse(
                status_code=401,
                content={"error": "Authentication failed"},
            )
            await response(scope, receive, send)
            return

        if result is None:
            # Auth backend returned None — no handler configured.
            # Pass through (consistent with how require_auth handles this
            # edge case, but allowing MCP to work when auth has no handler).
            await self._app(scope, receive, send)
            return

        _credentials, user_obj = result
        user = _to_user_model(user_obj)

        # Store in ContextVar for tool handlers to read
        token = _current_user.set(user)
        try:
            await self._app(scope, receive, send)
        finally:
            _current_user.reset(token)


def get_current_mcp_user() -> User:
    """Return the authenticated user for the current MCP request.

    Reads from the ``ContextVar`` set by ``_AuthMiddleware``.

    Returns:
        The authenticated ``User``.

    Raises:
        RuntimeError: If called outside of an authenticated MCP request.
    """
    user = _current_user.get()
    if user is None:
        raise RuntimeError("No authenticated user in MCP context")
    return user


class _AegraMCPServer(FastMCP):
    """FastMCP subclass that delegates tool listing and dispatch to MCPService.

    Tools are resolved dynamically on every request so no startup
    synchronisation is needed — by the time the first MCP request
    arrives the FastAPI lifespan has already initialised
    ``LangGraphService`` and the ``MCPService`` singleton is ready.
    """

    def __init__(self, service: MCPService) -> None:
        super().__init__(
            name="aegra",
            stateless_http=True,
            # Mount at "/" inside the sub-app so FastAPI's app.mount("/mcp", ...)
            # correctly routes POST /mcp to the MCP handler.
            streamable_http_path="/",
        )
        self._aegra_service = service

    async def list_tools(self) -> list[MCPTool]:
        """Return one MCPTool per registered graph, schema sourced live."""
        tool_defs: list[dict[str, Any]] = await self._aegra_service.list_tools()
        result: list[MCPTool] = []
        for td in tool_defs:
            result.append(
                MCPTool(
                    name=td["name"],
                    description=td.get("description", ""),
                    inputSchema=td.get("inputSchema", {"type": "object"}),
                )
            )
        return result

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[mcp_types.ContentBlock]:
        """Dispatch a tool call to MCPService with the authenticated user."""
        user = get_current_mcp_user()
        output: dict[str, Any] = await self._aegra_service.call_tool(name, arguments, user)
        return [mcp_types.TextContent(type="text", text=json.dumps(output))]


def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP Streamable HTTP endpoint at /mcp.

    Creates an ``_AegraMCPServer`` (FastMCP subclass), wraps it with
    auth middleware, and mounts the resulting Starlette ASGI app
    under ``/mcp`` on the FastAPI application.

    Authentication uses the same backend as Agent Protocol endpoints.

    Args:
        app: The FastAPI application to mount on.
    """
    service: MCPService = get_mcp_service()
    mcp_server = _AegraMCPServer(service)
    starlette_app = mcp_server.streamable_http_app()

    # Wrap with auth middleware so MCP requests go through the same
    # authentication as Agent Protocol endpoints.
    authed_app = _AuthMiddleware(starlette_app)

    app.mount("/mcp", authed_app)
    logger.info("MCP adapter mounted at /mcp (with auth)")
