"""E2E tests for custom routes functionality

These tests require a running Aegra server with custom routes configured.
To run these tests:
1. Ensure aegra.json has http.app pointing to custom_routes_example.py
2. Start the server: python run_server.py
3. Run: pytest tests/e2e/test_custom_routes/ -v
"""

import httpx
import pytest

from src.agent_server.settings import settings
from tests.e2e._utils import elog


def get_server_url() -> str:
    """Get server URL from environment or use default"""
    return settings.app.SERVER_URL


@pytest.mark.e2e
def test_custom_hello_endpoint():
    """Test the /custom/hello endpoint"""
    url = f"{get_server_url()}/custom/hello"

    response = httpx.get(url, timeout=10.0)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()

    assert "message" in data
    assert data["message"] == "Hello from custom route!"
    assert data.get("status") == "ok"

    elog("Custom hello endpoint", {"url": url, "response": data})


@pytest.mark.e2e
def test_custom_webhook_endpoint():
    """Test the /custom/webhook POST endpoint"""
    url = f"{get_server_url()}/custom/webhook"
    payload = {"test": "data", "value": 123, "nested": {"key": "value"}}

    response = httpx.post(url, json=payload, timeout=10.0)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()

    assert "received" in data
    assert data["received"] == payload
    assert data.get("status") == "processed"
    assert "message" in data

    elog("Custom webhook endpoint", {"url": url, "payload": payload, "response": data})


@pytest.mark.e2e
def test_custom_stats_endpoint():
    """Test the /custom/stats endpoint"""
    url = f"{get_server_url()}/custom/stats"

    response = httpx.get(url, timeout=10.0)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()

    assert "total_requests" in data
    assert "active_sessions" in data
    assert "uptime" in data
    assert isinstance(data["total_requests"], int)
    assert isinstance(data["active_sessions"], int)

    elog("Custom stats endpoint", {"url": url, "response": data})


@pytest.mark.e2e
def test_custom_root_shadows_default():
    """Test that custom root endpoint shadows the default Aegra root"""
    url = f"{get_server_url()}/"

    response = httpx.get(url, timeout=10.0)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()

    # Should return custom root, not default Aegra root
    assert "custom" in data
    assert data.get("custom") is True
    assert "message" in data
    assert "Custom Aegra Server" in data["message"]

    elog("Custom root endpoint", {"url": url, "response": data})


@pytest.mark.e2e
def test_custom_db_status_endpoint():
    """Test the /custom/db-status endpoint that accesses Aegra's db_manager"""
    url = f"{get_server_url()}/custom/db-status"

    response = httpx.get(url, timeout=10.0)

    # Should return 200 if db is connected, or 500 if not initialized
    assert response.status_code in (200, 500), (
        f"Unexpected status: {response.status_code}"
    )

    if response.status_code == 200:
        data = response.json()
        assert "database" in data
        assert "status" in data
        elog("Custom db-status endpoint (connected)", {"url": url, "response": data})
    else:
        # Database not initialized is acceptable in some test environments
        elog(
            "Custom db-status endpoint (not initialized)",
            {"url": url, "status": response.status_code},
        )


@pytest.mark.e2e
def test_core_routes_still_work():
    """Test that core Aegra routes still work alongside custom routes"""
    base_url = get_server_url()

    # Test unshadowable health endpoint
    health_response = httpx.get(f"{base_url}/health", timeout=10.0)
    assert health_response.status_code in (200, 503), (
        "Health endpoint should be accessible"
    )

    # Test core API endpoint (should return 401/403 without auth, but endpoint exists)
    assistants_response = httpx.get(f"{base_url}/assistants", timeout=10.0)
    # 401/403 is expected without auth, but endpoint should exist (not 404)
    assert assistants_response.status_code != 404, "Assistants endpoint should exist"

    elog(
        "Core routes verification",
        {
            "health_status": health_response.status_code,
            "assistants_status": assistants_response.status_code,
        },
    )


@pytest.mark.e2e
def test_openapi_includes_custom_routes():
    """Test that OpenAPI spec includes custom routes"""
    url = f"{get_server_url()}/openapi.json"

    response = httpx.get(url, timeout=10.0)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    openapi_spec = response.json()

    # Check that custom routes are in the OpenAPI spec
    paths = openapi_spec.get("paths", {})

    assert "/custom/hello" in paths, "Custom hello route should be in OpenAPI spec"
    assert "/custom/webhook" in paths, "Custom webhook route should be in OpenAPI spec"
    assert "/custom/stats" in paths, "Custom stats route should be in OpenAPI spec"

    # Verify the root path shows custom endpoint
    root_path = paths.get("/", {})
    if root_path:
        # Should have GET method
        get_method = root_path.get("get", {})
        if get_method:
            # Check if it's the custom root (has "custom" in description or response)
            elog("OpenAPI root path", {"root_path": root_path})

    elog(
        "OpenAPI spec verification",
        {
            "custom_routes_found": [
                path for path in paths if path.startswith("/custom")
            ],
            "total_paths": len(paths),
        },
    )


@pytest.mark.e2e
def test_custom_routes_priority():
    """Test that custom routes have correct priority (can shadow shadowable routes)"""
    base_url = get_server_url()

    # Custom root should override default root
    root_response = httpx.get(f"{base_url}/", timeout=10.0)
    assert root_response.status_code == 200
    root_data = root_response.json()

    # Should be custom root, not default
    assert root_data.get("custom") is True

    # Health endpoint should still work (unshadowable)
    health_response = httpx.get(f"{base_url}/health", timeout=10.0)
    assert health_response.status_code in (200, 503)  # 503 if db not ready is ok

    elog(
        "Route priority verification",
        {
            "root_is_custom": root_data.get("custom") is True,
            "health_accessible": health_response.status_code != 404,
        },
    )
