"""E2E tests for health check endpoints

These tests verify the new standardized health check endpoints work correctly
with the full application stack.

Note: These are basic smoke tests. The auth middleware prevents testing 404s
for old endpoints (returns 401 instead), which is acceptable behavior.
"""

import httpx
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_livez_endpoint():
    """Test /livez endpoint returns alive status"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/livez")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_readyz_endpoint():
    """Test /readyz endpoint checks all dependencies"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/readyz")
        # Should be either ready (200) or not ready (503)
        assert response.status_code in [200, 503]
        data = response.json()

        # Response structure
        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data
        assert data["status"] in ["ready", "not_ready"]

        # All dependencies should be present
        checks = data["checks"]
        assert "database" in checks
        assert "langgraph_checkpointer" in checks
        assert "langgraph_store" in checks
        assert "redis" in checks
        assert "model_armor" in checks
        assert "cache_worker" in checks
        assert "pinecone" in checks
        assert "crm" in checks

        # Each check should have proper structure
        for dep_name, check in checks.items():
            assert "status" in check
            assert "message" in check
            assert check["status"] in ["healthy", "unhealthy", "degraded"]

        if response.status_code == 200:
            assert data["status"] == "ready"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_healthz_endpoint():
    """Test /healthz endpoint (synonym for /readyz)"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/healthz")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ready", "not_ready"]
        assert "checks" in data
        assert "timestamp" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_info_endpoint_unchanged():
    """Test that /info endpoint still works as expected"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Aegra"
        assert data["status"] == "running"
        assert "version" in data
        assert "description" in data
        assert "flags" in data
