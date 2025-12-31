"""FastAPI application for Aegra (Agent Protocol Server)"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add graphs directory to Python path so react_agent can be imported
# This MUST happen before importing any modules that depend on graphs/
current_dir = Path(__file__).parent.parent.parent  # Go up to aegra root
graphs_dir = current_dir / "graphs"
if str(graphs_dir) not in sys.path:
    sys.path.insert(0, str(graphs_dir))

# ruff: noqa: E402 - imports below require sys.path modification above
import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount, Route

from .api.assistants import router as assistants_router
from .api.runs import router as runs_router
from .api.store import router as store_router
from .api.threads import router as threads_router
from .config import HttpConfig, load_http_config
from .core.app_loader import load_custom_app
from .core.auth_middleware import get_auth_backend, on_auth_error
from .core.database import db_manager
from .core.health import router as health_router
from .core.route_merger import (
    merge_exception_handlers,
    merge_lifespans,
    merge_routes,
    update_openapi_spec,
)
from .middleware import DoubleEncodedJSONMiddleware, StructLogMiddleware
from .models.errors import AgentProtocolError, get_error_type
from .observability.base import get_observability_manager
from .observability.langfuse_integration import _langfuse_provider
from .services.event_store import event_store
from .services.langgraph_service import get_langgraph_service
from .utils.setup_logging import setup_logging

# Task management for run cancellation
active_runs: dict[str, asyncio.Task] = {}

setup_logging()
logger = structlog.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context manager for startup/shutdown"""
    # Startup: Initialize database and LangGraph components
    await db_manager.initialize()

    # Initialize observability providers
    observability_manager = get_observability_manager()
    observability_manager.register_provider(_langfuse_provider)

    # Initialize LangGraph service
    langgraph_service = get_langgraph_service()
    await langgraph_service.initialize()

    # Initialize event store cleanup task
    await event_store.start_cleanup_task()

    yield

    # Shutdown: Clean up connections and cancel active runs
    for task in active_runs.values():
        if not task.done():
            task.cancel()

    # Stop event store cleanup task
    await event_store.stop_cleanup_task()

    await db_manager.close()


# Define core exception handlers
async def agent_protocol_exception_handler(
    _request: Request, exc: HTTPException
) -> JSONResponse:
    """Convert HTTP exceptions to Agent Protocol error format"""
    return JSONResponse(
        status_code=exc.status_code,
        content=AgentProtocolError(
            error=get_error_type(exc.status_code),
            message=exc.detail,
            details=getattr(exc, "details", None),
        ).model_dump(),
    )


async def general_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=500,
        content=AgentProtocolError(
            error="internal_error",
            message="An unexpected error occurred",
            details={"exception": str(exc)},
        ).model_dump(),
    )


exception_handlers = {
    HTTPException: agent_protocol_exception_handler,
    Exception: general_exception_handler,
}


# Define shadowable routes (can be overridden by custom routes)
async def root_handler() -> dict[str, str]:
    """Root endpoint"""
    return {"message": "Aegra", "version": "0.1.0", "status": "running"}


# Extract routes from health router - these are already Starlette-compatible
health_routes = [route for route in health_router.routes if hasattr(route, "path")]

# Filter routes by path for priority ordering
unshadowable_health_routes = [
    route for route in health_routes if route.path in ["/health", "/ready", "/live"]
]
shadowable_health_routes = [route for route in health_routes if route.path == "/info"]

shadowable_routes = [
    Route("/", root_handler, methods=["GET"]),
] + shadowable_health_routes

# Define unshadowable routes (health endpoints - always accessible)
unshadowable_routes = unshadowable_health_routes

# Create protected routes mount (core API routes)
# Extract routes from routers for the mount
protected_routes = []
for router in [assistants_router, threads_router, runs_router, store_router]:
    protected_routes.extend(router.routes)

protected_mount = Mount(
    "",
    routes=protected_routes,
    middleware=[
        Middleware(
            AuthenticationMiddleware, backend=get_auth_backend(), on_error=on_auth_error
        )
    ],
)

# Load HTTP configuration
http_config: HttpConfig | None = load_http_config()

# Try to load custom app if configured
user_app = None
if http_config and http_config.get("app"):
    try:
        user_app = load_custom_app(http_config["app"])
        logger.info("Custom app loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load custom app: {e}", exc_info=True)
        raise

# Create application
if user_app:
    # Merge custom app with Aegra routes
    app = user_app

    # Merge routes with priority order
    app = merge_routes(
        user_app=app,
        unshadowable_routes=unshadowable_routes,
        shadowable_routes=shadowable_routes,
        protected_mount=protected_mount,
    )

    # Merge lifespans
    app = merge_lifespans(app, lifespan)

    # Merge exception handlers
    app = merge_exception_handlers(app, exception_handlers)

    # Update OpenAPI spec if FastAPI
    update_openapi_spec(app)

    # Merge middleware - add Aegra middleware to user app
    # Note: User's middleware is already in user_app.user_middleware
    app.add_middleware(StructLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # Apply CORS configuration
    # Default expose_headers includes Content-Location and Location which are
    # required for LangGraph SDK stream reconnection (reconnectOnMount)
    cors_config = http_config.get("cors") if http_config else None
    default_expose_headers = ["Content-Location", "Location"]
    if cors_config:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.get("allow_origins", ["*"]),
            allow_credentials=cors_config.get("allow_credentials", True),
            allow_methods=cors_config.get("allow_methods", ["*"]),
            allow_headers=cors_config.get("allow_headers", ["*"]),
            expose_headers=cors_config.get("expose_headers", default_expose_headers),
            max_age=cors_config.get("max_age", 600),
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=default_expose_headers,
        )

    app.add_middleware(DoubleEncodedJSONMiddleware)

    # Apply auth middleware to custom routes if enabled
    enable_custom_route_auth = (
        http_config.get("enable_custom_route_auth", False) if http_config else False
    )
    if enable_custom_route_auth:
        app.add_middleware(
            AuthenticationMiddleware, backend=get_auth_backend(), on_error=on_auth_error
        )

else:
    # Standard Aegra app without custom routes
    app = FastAPI(
        title="Aegra",
        description="Production-ready Agent Protocol server built on LangGraph",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(StructLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # Add CORS middleware - apply config from http.cors if present
    # Default expose_headers includes Content-Location and Location which are
    # required for LangGraph SDK stream reconnection (reconnectOnMount)
    cors_config = http_config.get("cors") if http_config else None
    default_expose_headers = ["Content-Location", "Location"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.get("allow_origins", ["*"]) if cors_config else ["*"],
        allow_credentials=cors_config.get("allow_credentials", True)
        if cors_config
        else True,
        allow_methods=cors_config.get("allow_methods", ["*"]) if cors_config else ["*"],
        allow_headers=cors_config.get("allow_headers", ["*"]) if cors_config else ["*"],
        expose_headers=cors_config.get("expose_headers", default_expose_headers)
        if cors_config
        else default_expose_headers,
        max_age=cors_config.get("max_age", 600) if cors_config else 600,
    )

    # Add middleware to handle double-encoded JSON from frontend
    app.add_middleware(DoubleEncodedJSONMiddleware)

    # Add authentication middleware (must be added after CORS)
    app.add_middleware(
        AuthenticationMiddleware, backend=get_auth_backend(), on_error=on_auth_error
    )

    # Include routers
    app.include_router(health_router, prefix="", tags=["Health"])
    app.include_router(assistants_router, prefix="", tags=["Assistants"])
    app.include_router(threads_router, prefix="", tags=["Threads"])
    app.include_router(runs_router, prefix="", tags=["Runs"])
    app.include_router(store_router, prefix="", tags=["Store"])

    # Add exception handlers
    for exc_type, handler in exception_handlers.items():
        app.exception_handler(exc_type)(handler)

    # Add root endpoint
    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint"""
        return {"message": "Aegra", "version": "0.1.0", "status": "running"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec B104 - binding to all interfaces is intentional
