"""Health check endpoints"""

import contextlib
import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class LivenessResponse(BaseModel):
    """Liveness check response model"""

    status: Literal["alive"]


class ReadinessResponse(BaseModel):
    """Readiness check response model"""

    status: Literal["ready", "not_ready"]
    database: str
    langgraph_checkpointer: str
    langgraph_store: str
    redis: str


class DetailedHealthResponse(BaseModel):
    """Detailed health check response model"""

    status: Literal["healthy", "unhealthy"]
    critical: dict[str, str]
    optional: dict[str, str]


class InfoResponse(BaseModel):
    """Info endpoint response model"""

    name: str
    version: str
    description: str
    status: str
    flags: dict


@router.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    """Simple service information endpoint"""
    return InfoResponse(
        name="Aegra",
        version="0.1.0",
        description="Production-ready Agent Protocol server built on LangGraph",
        status="running",
        flags={"assistants": True, "crons": False},
    )


@router.get("/livez", response_model=LivenessResponse)
async def liveness_check() -> LivenessResponse:
    """Kubernetes liveness probe endpoint - basic process health"""
    return LivenessResponse(status="alive")


async def _check_critical_dependencies() -> dict[str, str]:
    """Check all critical dependencies and return their status.

    Returns:
        Dictionary with status for each critical dependency
    """
    from sqlalchemy import text

    from .database import db_manager

    statuses = {
        "database": "unknown",
        "langgraph_checkpointer": "unknown",
        "langgraph_store": "unknown",
        "redis": "unknown",
    }

    # Database connectivity
    try:
        if db_manager.engine:
            async with db_manager.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            statuses["database"] = "connected"
        else:
            statuses["database"] = "not_initialized"
    except Exception as e:
        statuses["database"] = f"error: {str(e)}"

    # LangGraph checkpointer
    try:
        checkpointer = await db_manager.get_checkpointer()
        with contextlib.suppress(Exception):
            await checkpointer.aget_tuple(
                {"configurable": {"thread_id": "health-check"}}
            )
        statuses["langgraph_checkpointer"] = "connected"
    except Exception as e:
        statuses["langgraph_checkpointer"] = f"error: {str(e)}"

    # LangGraph store
    try:
        store = await db_manager.get_store()
        with contextlib.suppress(Exception):
            await store.aget(("health",), "check")
        statuses["langgraph_store"] = "connected"
    except Exception as e:
        statuses["langgraph_store"] = f"error: {str(e)}"

    # Redis (now CRITICAL)
    try:
        from graphs.ava_v1.shared_libraries.redis_client import get_redis_client

        redis_client = get_redis_client()
        await redis_client.ping()
        statuses["redis"] = "connected"
    except ImportError:
        statuses["redis"] = "not_available"
    except Exception as e:
        statuses["redis"] = f"error: {str(e)}"

    return statuses


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """Kubernetes readiness probe endpoint - all critical dependencies must be healthy"""
    statuses = await _check_critical_dependencies()

    # Check if any critical dependency failed
    is_ready = all(
        status == "connected" or status == "not_available"
        for status in statuses.values()
    )

    if is_ready:
        return ReadinessResponse(status="ready", **statuses)
    else:
        response = ReadinessResponse(status="not_ready", **statuses)
        raise HTTPException(status_code=503, detail=response.model_dump())


@router.get("/healthz", response_model=ReadinessResponse)
async def healthz_check() -> ReadinessResponse:
    """Health check endpoint - synonym for readiness check"""
    return await readiness_check()


async def _check_model_armor() -> str:
    """Check Model Armor API connectivity"""
    try:
        env_mode = os.getenv("ENV_MODE", "")
        enabled = os.getenv("MODEL_ARMOR_ENABLED", "").lower() == "true"

        if env_mode != "PRODUCTION" and not enabled:
            return "not_configured"

        project_id = os.getenv("MODEL_ARMOR_PROJECT_ID")
        if not project_id:
            return "not_configured"

        from graphs.ava_v1.middleware.model_armor_client import _get_credentials

        _get_credentials()
        return "connected"
    except ImportError:
        return "not_configured"
    except Exception as e:
        return f"error: {str(e)}"


async def _check_cache_worker() -> str:
    """Check Cache Worker API connectivity"""
    try:
        from graphs.ava_v1.shared_libraries.cache_worker_client import (
            get_cache_worker_base_url,
        )

        base_url = get_cache_worker_base_url()
        if not base_url:
            return "not_configured"

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/health", timeout=2.0)
            response.raise_for_status()
            return "connected"
    except ImportError:
        return "not_configured"
    except Exception as e:
        return f"error: {str(e)}"


async def _check_pinecone() -> str:
    """Check Pinecone service connectivity"""
    try:
        pinecone_url = os.getenv("PINECONE_SERVICE_URL")
        if not pinecone_url:
            return "not_configured"

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{pinecone_url}/health", timeout=2.0)
            response.raise_for_status()
            return "connected"
    except Exception as e:
        return f"error: {str(e)}"


async def _check_crm() -> str:
    """Check CRM API availability"""
    try:
        enabled = os.getenv("CRM_LOOKUP_ENABLED", "").lower() == "true"
        if not enabled:
            return "not_configured"

        base_url = os.getenv("CRM_BASE_URL")
        api_key = os.getenv("CRM_API_KEY")

        if not base_url or not api_key:
            return "error: missing configuration"

        return "configured"
    except Exception as e:
        return f"error: {str(e)}"


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check() -> DetailedHealthResponse:
    """Comprehensive health check with critical and optional dependencies"""
    # Check critical dependencies
    critical_statuses = await _check_critical_dependencies()

    # Check optional dependencies
    optional_statuses = {
        "model_armor": await _check_model_armor(),
        "cache_worker": await _check_cache_worker(),
        "pinecone": await _check_pinecone(),
        "crm": await _check_crm(),
    }

    # Determine overall health based on critical dependencies only
    is_healthy = all(
        status == "connected" or status == "not_available"
        for status in critical_statuses.values()
    )

    if is_healthy:
        return DetailedHealthResponse(
            status="healthy", critical=critical_statuses, optional=optional_statuses
        )
    else:
        response = DetailedHealthResponse(
            status="unhealthy", critical=critical_statuses, optional=optional_statuses
        )
        raise HTTPException(status_code=503, detail=response.model_dump())
