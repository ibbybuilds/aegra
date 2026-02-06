"""Health check endpoints"""

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Callable, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()


class CheckResult(BaseModel):
    """Result of a single health check"""

    status: Literal["healthy", "unhealthy", "degraded"]
    message: str
    error: str | None = None


class LivenessResponse(BaseModel):
    """Liveness check response model"""

    status: Literal["healthy"]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ReadinessResponse(BaseModel):
    """Readiness check response model"""

    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


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
    return LivenessResponse(status="healthy")


async def _run_check_with_timeout(
    check_func: Callable, timeout: float = 2.0
) -> CheckResult:
    """Wrap check function with timeout protection.

    Args:
        check_func: Async function that returns a CheckResult
        timeout: Maximum time in seconds to wait for check

    Returns:
        CheckResult from the check function or timeout error
    """
    try:
        return await asyncio.wait_for(check_func(), timeout=timeout)
    except asyncio.TimeoutError:
        return CheckResult(
            status="unhealthy",
            message="Check timed out",
            error=f"timeout after {timeout} seconds",
        )


async def _check_database() -> CheckResult:
    """Check database connectivity.

    Returns:
        CheckResult with database status
    """
    from sqlalchemy import text

    from .database import db_manager

    try:
        if not db_manager.engine:
            return CheckResult(
                status="unhealthy",
                message="Not initialized",
                error="database engine not initialized",
            )

        async with db_manager.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

        return CheckResult(status="healthy", message="Connected")
    except Exception as e:
        return CheckResult(
            status="unhealthy", message="Connection failed", error=str(e)
        )


async def _check_langgraph_checkpointer() -> CheckResult:
    """Check LangGraph checkpointer connectivity.

    Returns:
        CheckResult with checkpointer status
    """
    from .database import db_manager

    try:
        checkpointer = await db_manager.get_checkpointer()
        with contextlib.suppress(Exception):
            await checkpointer.aget_tuple(
                {"configurable": {"thread_id": "health-check"}}
            )
        return CheckResult(status="healthy", message="Connected")
    except Exception as e:
        return CheckResult(
            status="unhealthy", message="Connection failed", error=str(e)
        )


async def _check_langgraph_store() -> CheckResult:
    """Check LangGraph store connectivity.

    Returns:
        CheckResult with store status
    """
    from .database import db_manager

    try:
        store = await db_manager.get_store()
        with contextlib.suppress(Exception):
            await store.aget(("health",), "check")
        return CheckResult(status="healthy", message="Connected")
    except Exception as e:
        return CheckResult(
            status="unhealthy", message="Connection failed", error=str(e)
        )


async def _check_redis() -> CheckResult:
    """Check Redis connectivity (critical for ava_v1 graph).

    Returns:
        CheckResult with Redis status
    """
    try:
        from graphs.ava_v1.shared_libraries.redis_client import get_redis_client

        redis_client = get_redis_client()
        await redis_client.ping()
        return CheckResult(status="healthy", message="Connected")
    except ImportError:
        # ava_v1 graph not loaded - Redis not required
        return CheckResult(status="healthy", message="Not required")
    except Exception as e:
        return CheckResult(
            status="unhealthy", message="Connection failed", error=str(e)
        )


async def _check_all_dependencies() -> dict[str, CheckResult]:
    """Check all dependencies (both critical and non-critical).

    Returns:
        Dictionary mapping dependency name to CheckResult
    """
    # Run all checks with timeout protection
    checks = {}

    # Critical dependencies
    checks["database"] = await _run_check_with_timeout(_check_database)
    checks["langgraph_checkpointer"] = await _run_check_with_timeout(
        _check_langgraph_checkpointer
    )
    checks["langgraph_store"] = await _run_check_with_timeout(_check_langgraph_store)
    checks["redis"] = await _run_check_with_timeout(_check_redis)

    # Non-critical dependencies
    checks["model_armor"] = await _run_check_with_timeout(_check_model_armor)
    checks["cache_worker"] = await _run_check_with_timeout(_check_cache_worker)
    checks["pinecone"] = await _run_check_with_timeout(_check_pinecone)
    checks["crm"] = await _run_check_with_timeout(_check_crm)

    return checks


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check():
    """Kubernetes readiness probe endpoint - all critical dependencies must be healthy"""
    checks = await _check_all_dependencies()

    # Critical dependencies that must be healthy
    critical_deps = ["database", "langgraph_checkpointer", "langgraph_store", "redis"]

    # Check if any critical dependency is unhealthy
    has_critical_failure = any(
        checks[dep].status == "unhealthy" for dep in critical_deps
    )

    response = ReadinessResponse(
        status="not_ready" if has_critical_failure else "ready",
        checks=checks
    )

    status_code = 503 if has_critical_failure else 200
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json")
    )


@router.get("/healthz", response_model=ReadinessResponse)
async def healthz_check() -> ReadinessResponse:
    """Health check endpoint - synonym for readiness check"""
    return await readiness_check()


async def _check_model_armor() -> CheckResult:
    """Check Model Armor API connectivity (non-critical).

    Returns:
        CheckResult with Model Armor status
    """
    try:
        env_mode = os.getenv("ENV_MODE", "")
        enabled = os.getenv("MODEL_ARMOR_ENABLED", "").lower() == "true"

        # Model Armor is auto-enabled in PRODUCTION or can be explicitly enabled
        is_enabled = env_mode == "PRODUCTION" or enabled

        if not is_enabled:
            return CheckResult(status="degraded", message="Disabled")

        # Check required configuration
        project_id = os.getenv("MODEL_ARMOR_PROJECT_ID")
        template_id = os.getenv("MODEL_ARMOR_TEMPLATE_ID")

        if not project_id or not template_id:
            missing = []
            if not project_id:
                missing.append("MODEL_ARMOR_PROJECT_ID")
            if not template_id:
                missing.append("MODEL_ARMOR_TEMPLATE_ID")
            return CheckResult(
                status="degraded",
                message="Configuration incomplete",
                error=f"missing {', '.join(missing)}",
            )

        # Configuration is present - don't actually call GCP to avoid auth issues in health check
        return CheckResult(status="healthy", message="Configured")
    except ImportError:
        return CheckResult(status="degraded", message="Not configured")
    except Exception as e:
        return CheckResult(status="degraded", message="Service unavailable", error=str(e))


async def _check_cache_worker() -> CheckResult:
    """Check Cache Worker API connectivity (non-critical).

    Returns:
        CheckResult with Cache Worker status
    """
    try:
        from graphs.ava_v1.shared_libraries.cache_worker_client import (
            get_cache_worker_base_url,
        )

        base_url = get_cache_worker_base_url()
        if not base_url:
            return CheckResult(status="degraded", message="Not configured")

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/health", timeout=2.0)
            response.raise_for_status()
            return CheckResult(status="healthy", message="Connected")
    except ImportError:
        return CheckResult(status="degraded", message="Not configured")
    except Exception as e:
        return CheckResult(status="degraded", message="Service unavailable", error=str(e))


async def _check_pinecone() -> CheckResult:
    """Check Pinecone service connectivity (non-critical).

    Returns:
        CheckResult with Pinecone status
    """
    try:
        pinecone_url = os.getenv("PINECONE_SERVICE_URL")
        if not pinecone_url:
            return CheckResult(status="degraded", message="Not configured")

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{pinecone_url}/health", timeout=2.0)
            response.raise_for_status()
            return CheckResult(status="healthy", message="Connected")
    except Exception as e:
        return CheckResult(status="degraded", message="Service unavailable", error=str(e))


async def _check_crm() -> CheckResult:
    """Check CRM API availability (non-critical).

    Returns:
        CheckResult with CRM status
    """
    try:
        # Check if CRM lookup is enabled (defaults to true)
        enabled = os.getenv("CRM_LOOKUP_ENABLED", "true").lower() == "true"
        if not enabled:
            return CheckResult(status="degraded", message="Disabled")

        # CRM auto-selects base_url based on ENV_MODE if not explicitly set
        # So we only need to check for JWT secret
        jwt_secret = os.getenv("CRM_JWT_SECRET")
        if not jwt_secret:
            return CheckResult(
                status="degraded",
                message="Configuration incomplete",
                error="missing CRM_JWT_SECRET",
            )

        return CheckResult(status="healthy", message="Configured")
    except Exception as e:
        return CheckResult(status="degraded", message="Service unavailable", error=str(e))


