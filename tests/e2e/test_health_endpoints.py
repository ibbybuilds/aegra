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
        assert data["status"] == "alive"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_readyz_endpoint():
    """Test /readyz endpoint checks all critical dependencies"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/readyz")
        # Should be either ready (200) or not ready (503)
        assert response.status_code in [200, 503]
        data = response.json()

        # All critical dependencies should be present
        assert "status" in data
        assert "database" in data
        assert "langgraph_checkpointer" in data
        assert "langgraph_store" in data
        assert "redis" in data

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


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_health_detailed_endpoint():
    """Test /health/detailed endpoint with comprehensive checks"""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/health/detailed")
        assert response.status_code in [200, 503]
        data = response.json()

        # Should have both sections
        assert "status" in data
        assert "critical" in data
        assert "optional" in data

        # Critical dependencies
        critical = data["critical"]
        assert "database" in critical
        assert "langgraph_checkpointer" in critical
        assert "langgraph_store" in critical
        assert "redis" in critical

        # Optional dependencies
        optional = data["optional"]
        assert "model_armor" in optional
        assert "cache_worker" in optional
        assert "pinecone" in optional
        assert "crm" in optional


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
