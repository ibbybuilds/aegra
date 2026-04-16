"""Integration tests for health and info endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegra_api.core.health import router
from aegra_api.settings import settings


def test_info_reports_cron_flag_from_runtime_settings(monkeypatch) -> None:
    """GET /info should expose the current CRON_ENABLED runtime flag."""
    app = FastAPI()
    app.include_router(router)

    monkeypatch.setattr(settings.cron, "CRON_ENABLED", False)

    client = TestClient(app)
    response = client.get("/info")

    assert response.status_code == 200
    assert response.json()["flags"] == {"assistants": True, "crons": False}
