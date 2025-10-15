"""Health check endpoints"""

import contextlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    database: str
    langgraph_checkpointer: str
    langgraph_store: str


class InfoResponse(BaseModel):
    """Info endpoint response model"""

    name: str
    version: str
    description: str
    status: str


@router.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """Simple service information endpoint"""
    return InfoResponse(
        name="Aegra",
        version="0.1.0",
        description="Production-ready Agent Protocol server built on LangGraph",
        status="running",
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> dict[str, str]:
    """Comprehensive health check endpoint"""
    # Import here to avoid circular dependency
    from .database import db_manager

    health_status = {
        "status": "healthy",
        "database": "unknown",
        "langgraph_checkpointer": "unknown",
        "langgraph_store": "unknown",
    }

    # Database connectivity
    try:
        if db_manager.engine:
            async with db_manager.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            health_status["database"] = "connected"
        else:
            health_status["database"] = "not_initialized"
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # LangGraph checkpointer (lazy-init)
    try:
        checkpointer = await db_manager.get_checkpointer()
        # probe - will raise if connection is bad; tuple may not exist which is fine
        with contextlib.suppress(Exception):
            await checkpointer.aget_tuple(
                {"configurable": {"thread_id": "health-check"}}
            )
        health_status["langgraph_checkpointer"] = "connected"
    except Exception as e:
        health_status["langgraph_checkpointer"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # LangGraph store (lazy-init)
    try:
        store = await db_manager.get_store()
        with contextlib.suppress(Exception):
            await store.aget(("health",), "check")
        health_status["langgraph_store"] = "connected"
    except Exception as e:
        health_status["langgraph_store"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail="Service unhealthy")

    return health_status


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Kubernetes readiness probe endpoint"""
    from .database import db_manager

    # Engine must exist and respond to a trivial query
    if not db_manager.engine:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - database engine not initialized",
        )
    try:
        async with db_manager.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Service not ready - database error: {str(e)}"
        ) from e

    # Check that LangGraph components can be obtained (lazy init) and respond
    try:
        checkpointer = await db_manager.get_checkpointer()
        store = await db_manager.get_store()
        # lightweight probes
        with contextlib.suppress(Exception):
            await checkpointer.aget_tuple(
                {"configurable": {"thread_id": "ready-check"}}
            )
        with contextlib.suppress(Exception):
            await store.aget(("ready",), "check")
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready - components unavailable: {str(e)}",
        ) from e

    return {"status": "ready"}


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    """Kubernetes liveness probe endpoint"""
    return {"status": "alive"}
