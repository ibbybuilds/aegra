"""E2E tests for the Prometheus /metrics endpoint.

Requires a running server with ENABLE_PROMETHEUS_METRICS=true.
"""

import httpx
import pytest

from aegra_api.settings import settings


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format() -> None:
    """Test that /metrics returns Prometheus exposition text from a real server."""
    server_url = settings.app.SERVER_URL

    async with httpx.AsyncClient(base_url=server_url, timeout=5.0) as client:
        # Make a request so there's something to report
        await client.get("/health")

        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        body = response.text
        assert "http_request_duration" in body or "http_requests" in body
