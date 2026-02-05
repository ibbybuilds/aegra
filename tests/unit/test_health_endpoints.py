"""Unit tests for health check endpoints"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_livez_always_returns_alive():
    """Test that /livez always returns alive status"""
    from src.agent_server.core.health import liveness_check

    response = await liveness_check()
    assert response.status == "healthy"
    assert response.timestamp
    assert "T" in response.timestamp


@pytest.mark.asyncio
async def test_readyz_success_all_dependencies_healthy():
    """Test that /readyz returns 200 when all critical dependencies pass"""
    from src.agent_server.core.health import CheckResult, readiness_check

    # Mock all dependencies as healthy
    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "healthy"
        assert data["checks"]["langgraph_checkpointer"]["status"] == "healthy"
        assert data["checks"]["langgraph_store"]["status"] == "healthy"
        assert data["checks"]["redis"]["status"] == "healthy"
        assert "timestamp" in data
        assert "T" in data["timestamp"]


@pytest.mark.asyncio
async def test_readyz_failure_database_error():
    """Test that /readyz returns 503 when database fails"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(
                status="unhealthy",
                message="Connection failed",
                error="connection timeout",
            ),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 503
        data = json.loads(response.body)
        assert data["status"] == "not_ready"


@pytest.mark.asyncio
async def test_readyz_failure_langgraph_checkpointer_error():
    """Test that /readyz returns 503 when LangGraph checkpointer fails"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(
                status="unhealthy",
                message="Connection failed",
                error="connection refused",
            ),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 503
        data = json.loads(response.body)
        assert data["status"] == "not_ready"


@pytest.mark.asyncio
async def test_readyz_failure_langgraph_store_error():
    """Test that /readyz returns 503 when LangGraph store fails"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(
                status="unhealthy", message="Connection failed", error="timeout"
            ),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 503
        data = json.loads(response.body)
        assert data["status"] == "not_ready"


@pytest.mark.asyncio
async def test_readyz_failure_redis_error():
    """Test that /readyz returns 503 when Redis is unavailable (critical)"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(
                status="unhealthy",
                message="Connection failed",
                error="connection refused",
            ),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 503
        data = json.loads(response.body)
        assert data["status"] == "not_ready"


@pytest.mark.asyncio
async def test_readyz_success_redis_not_required():
    """Test that /readyz returns 200 when Redis is not required (ava_v1 not loaded)"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Not required"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "ready"
        assert data["checks"]["redis"]["status"] == "healthy"
        assert data["checks"]["redis"]["message"] == "Not required"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_healthz_identical_to_readyz():
    """Test that /healthz behaves identically to /readyz"""
    from src.agent_server.core.health import CheckResult, healthz_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(status="degraded", message="Not configured"),
            "cache_worker": CheckResult(status="degraded", message="Not configured"),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await healthz_check()
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "healthy"
        assert data["checks"]["langgraph_checkpointer"]["status"] == "healthy"
        assert data["checks"]["langgraph_store"]["status"] == "healthy"
        assert data["checks"]["redis"]["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_readyz_success_with_degraded_non_critical():
    """Test that /readyz returns 200 when critical deps are healthy but optional are degraded"""
    from src.agent_server.core.health import CheckResult, readiness_check

    with patch(
        "src.agent_server.core.health._check_all_dependencies"
    ) as mock_check:
        mock_check.return_value = {
            "database": CheckResult(status="healthy", message="Connected"),
            "langgraph_checkpointer": CheckResult(status="healthy", message="Connected"),
            "langgraph_store": CheckResult(status="healthy", message="Connected"),
            "redis": CheckResult(status="healthy", message="Connected"),
            "model_armor": CheckResult(
                status="degraded",
                message="Service unavailable",
                error="connection refused",
            ),
            "cache_worker": CheckResult(
                status="degraded",
                message="Service unavailable",
                error="timeout after 2 seconds",
            ),
            "pinecone": CheckResult(status="degraded", message="Not configured"),
            "crm": CheckResult(status="degraded", message="Not configured"),
        }

        response = await readiness_check()
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "healthy"
        assert data["checks"]["model_armor"]["status"] == "degraded"
        assert data["checks"]["cache_worker"]["status"] == "degraded"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_timeout_protection():
    """Test that checks are protected by timeout wrapper"""
    import asyncio

    from src.agent_server.core.health import _run_check_with_timeout

    async def slow_check():
        await asyncio.sleep(5)
        from src.agent_server.core.health import CheckResult

        return CheckResult(status="healthy", message="Connected")

    result = await _run_check_with_timeout(slow_check, timeout=0.1)
    assert result.status == "unhealthy"
    assert result.message == "Check timed out"
    assert "timeout" in result.error


@pytest.mark.asyncio
async def test_optional_dependencies_not_configured():
    """Test optional dependency checks return degraded when disabled"""
    from src.agent_server.core.health import (
        _check_cache_worker,
        _check_crm,
        _check_model_armor,
        _check_pinecone,
    )

    with patch.dict("os.environ", {}, clear=True):
        # Model Armor not in production and not enabled
        armor_result = await _check_model_armor()
        assert armor_result.status == "degraded"
        assert armor_result.message == "Not configured"

        # Cache Worker - missing URL
        cache_result = await _check_cache_worker()
        assert cache_result.status == "degraded"
        assert cache_result.message == "Not configured"

        # Pinecone - missing URL
        pinecone_result = await _check_pinecone()
        assert pinecone_result.status == "degraded"
        assert pinecone_result.message == "Not configured"

        # CRM - not enabled
        crm_result = await _check_crm()
        assert crm_result.status == "degraded"
        assert crm_result.message == "Not configured"


@pytest.mark.asyncio
async def test_check_database_success():
    """Test _check_database correctly checks database connectivity"""
    from src.agent_server.core.health import _check_database

    # Create mock database manager
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_engine.begin = MagicMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock()

    with patch("src.agent_server.core.database.db_manager") as mock_db_manager:
        mock_db_manager.engine = mock_engine

        result = await _check_database()

        assert result.status == "healthy"
        assert result.message == "Connected"


@pytest.mark.asyncio
async def test_check_redis_import_error():
    """Test Redis returns healthy when ava_v1 is not loaded"""
    from src.agent_server.core.health import _check_redis

    # Mock the import to raise ImportError (simulating ava_v1 not loaded)
    import sys
    from unittest.mock import MagicMock

    mock_module = MagicMock()
    mock_module.get_redis_client.side_effect = ImportError

    with patch.dict(sys.modules, {"graphs.ava_v1.shared_libraries.redis_client": None}):
        result = await _check_redis()
        assert result.status == "healthy"
        assert result.message == "Not required"


@pytest.mark.asyncio
async def test_pinecone_check_success():
    """Test Pinecone health check success"""
    from src.agent_server.core.health import _check_pinecone

    with patch.dict(
        "os.environ", {"PINECONE_SERVICE_URL": "http://pinecone:8080"}
    ), patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock()
        mock_client.return_value = mock_client_instance

        result = await _check_pinecone()
        assert result.status == "healthy"
        assert result.message == "Connected"


@pytest.mark.asyncio
async def test_crm_check_configured():
    """Test CRM check when properly configured"""
    from src.agent_server.core.health import _check_crm

    with patch.dict(
        "os.environ",
        {
            "CRM_LOOKUP_ENABLED": "true",
            "CRM_BASE_URL": "https://crm.example.com",
            "CRM_API_KEY": "test-key",
        },
    ):
        result = await _check_crm()
        assert result.status == "healthy"
        assert result.message == "Configured"


@pytest.mark.asyncio
async def test_crm_check_missing_config():
    """Test CRM check with missing configuration"""
    from src.agent_server.core.health import _check_crm

    with patch.dict(
        "os.environ",
        {"CRM_LOOKUP_ENABLED": "true"},
        clear=True,
    ):
        result = await _check_crm()
        assert result.status == "degraded"
        assert result.message == "Configuration incomplete"
        assert "missing" in result.error
