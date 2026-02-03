"""E2E tests for custom routes functionality

These tests require a running Aegra server with custom routes configured.
To run these tests:
1. Ensure aegra.json has http.app pointing to custom_routes_example.py
2. Start the server: python run_server.py
3. Run: pytest tests/e2e/test_custom_routes/ -v
"""

import httpx
import pytest

from aegra_api.settings import settings
from tests.e2e._utils import elog


def get_server_url() -> str:
    """Get server URL from environment or use default"""
    return settings.app.SERVER_URL


@pytest.mark.e2e
def test_core_routes_still_work():
    """Test that core Aegra routes still work alongside custom routes"""
    base_url = get_server_url()

    # Test unshadowable health endpoint
    health_response = httpx.get(f"{base_url}/health", timeout=10.0)
    assert health_response.status_code in (200, 503), "Health endpoint should be accessible"

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
    """Test that OpenAPI spec includes custom routes from custom_routes_example.py"""
    url = f"{get_server_url()}/openapi.json"

    response = httpx.get(url, timeout=10.0)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    openapi_spec = response.json()

    # Check that custom routes from custom_routes_example.py are in the OpenAPI spec
    paths = openapi_spec.get("paths", {})

    # These routes exist in custom_routes_example.py
    assert "/custom/whoami" in paths, "Custom whoami route should be in OpenAPI spec"
    assert "/custom/public" in paths, "Custom public route should be in OpenAPI spec"
    assert "/custom/protected" in paths, "Custom protected route should be in OpenAPI spec"

    elog(
        "OpenAPI spec verification",
        {
            "custom_routes_found": [path for path in paths if path.startswith("/custom")],
            "total_paths": len(paths),
        },
    )
