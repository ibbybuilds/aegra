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
from starlette.middleware.authentication import AuthenticationMiddleware

from .api.activity_logs import router as activity_logs_router
from .api.assistants import router as assistants_router
from .api.career_advisors import router as career_advisors_router
from .api.management import router as management_router
from .api.runs import router as runs_router
from .api.store import router as store_router
from .api.threads import router as threads_router
from .core.auth_middleware import get_auth_backend, on_auth_error
from .core.database import db_manager
from .core.health import router as health_router
from .core.redis import redis_manager
from .middleware import DoubleEncodedJSONMiddleware, StructLogMiddleware
from .models.errors import AgentProtocolError, get_error_type
from .services.broker import broker_manager
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

    # Initialize Redis if configured
    await redis_manager.initialize()

    # Initialize LangGraph service
    langgraph_service = get_langgraph_service()
    await langgraph_service.initialize()

    # Initialize event store cleanup task
    await event_store.start_cleanup_task()
    await broker_manager.start_cleanup_task()
    broker_manager.validate_configuration()

    yield

    # Shutdown: Clean up connections and cancel active runs
    for task in active_runs.values():
        if not task.done():
            task.cancel()

    # Stop event store cleanup task
    await event_store.stop_cleanup_task()
    await broker_manager.stop_cleanup_task()

    # Close Redis connection if configured
    await redis_manager.close()

    await db_manager.close()


# Create FastAPI application
app = FastAPI(
    title="Aegra",
    description="Aegra: Production-ready Agent Protocol server built on LangGraph",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    # Increase max request size for file uploads (50MB)
    # Note: This is a Starlette limit, not Uvicorn
)

# Define security scheme for Bearer token authentication
from fastapi.openapi.utils import get_openapi

# Paths that don't require authentication (no padlock)
PUBLIC_PATHS = {
    "/",
    "/health",
    "/health/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/live",
    "/info",
    "/ready",
    "/favicon.ico",
}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token",
        }
    }
    # Apply security to each path individually (skip public paths)
    for path, methods in openapi_schema.get("paths", {}).items():
        if path not in PUBLIC_PATHS:
            for method in methods.values():
                if isinstance(method, dict):
                    method["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(StructLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(activity_logs_router, prefix="", tags=["Activity Logs"])
app.include_router(management_router, prefix="", tags=["Management"])
app.include_router(career_advisors_router, prefix="", tags=["Career Advisors"])


# Error handling
@app.exception_handler(HTTPException)
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


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    """Handle JSON decode and validation errors"""
    error_msg = str(exc)
    logger.error(f"Validation error: {error_msg}")

    # Check if it's a JSON decode error
    if "JSON" in error_msg or "json" in error_msg.lower():
        return JSONResponse(
            status_code=400,
            content=AgentProtocolError(
                error="invalid_request",
                message="Invalid JSON in request body. Ensure file content is properly encoded.",
                details={"error": error_msg},
            ).model_dump(),
        )

    return JSONResponse(
        status_code=400,
        content=AgentProtocolError(
            error="validation_error",
            message=error_msg,
            details={"exception": str(exc)},
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger.exception("Unexpected error")
    return JSONResponse(
        status_code=500,
        content=AgentProtocolError(
            error="internal_error",
            message="An unexpected error occurred",
            details={"exception": str(exc)},
        ).model_dump(),
    )


@app.get("/")
@app.head("/")
async def root() -> dict[str, str]:
    """Root endpoint - supports GET and HEAD for health checks"""
    return {"message": "Aegra", "version": "0.1.0", "status": "running"}


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec B104 - binding to all interfaces is intentional
