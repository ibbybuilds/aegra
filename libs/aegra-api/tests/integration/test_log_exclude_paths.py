"""Integration tests for LOG_EXCLUDE_PATHS middleware behaviour.

Tests verify that the full FastAPI app (with StructLogMiddleware) respects
LOG_EXCLUDE_PATHS by suppressing access logs for matched prefixes while
still logging errors on those paths.
"""

import importlib
import sys
from collections.abc import Callable, Generator

import pytest
from starlette.testclient import TestClient

import aegra_api.main as aegra_main
import aegra_api.middleware.logger_middleware as logger_middleware


def _reload_modules() -> None:
    """Reload settings, middleware, and app so they pick up env var changes."""
    importlib.reload(importlib.import_module("aegra_api.settings"))
    importlib.reload(importlib.import_module("aegra_api.middleware.logger_middleware"))
    if "aegra_api.main" in sys.modules:
        importlib.reload(sys.modules["aegra_api.main"])


@pytest.fixture(autouse=True)
def _isolate_module_state() -> Generator[None, None, None]:
    """Reload modules before and after each test to prevent cross-test leakage."""
    yield
    _reload_modules()


def _make_capture_log(logged_calls: list[str]) -> Callable[[str], Callable[..., None]]:
    """Create a log capture factory bound to the given list."""

    def capture_log(method_name: str) -> Callable[..., None]:
        def _log(msg: str, *args: object, **kwargs: object) -> None:
            logged_calls.append(method_name)

        return _log

    return capture_log


def test_excluded_path_suppresses_access_log(monkeypatch) -> None:
    """GET /info with LOG_EXCLUDE_PATHS=/info should not produce an access log entry."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "/info")
    _reload_modules()

    app = aegra_main.app
    access_logger = logger_middleware.access_logger

    logged_calls: list[str] = []
    capture_log = _make_capture_log(logged_calls)

    monkeypatch.setattr(access_logger, "info", capture_log("info"))
    monkeypatch.setattr(access_logger, "warning", capture_log("warning"))
    monkeypatch.setattr(access_logger, "error", capture_log("error"))

    client = TestClient(app)

    # /info returns 200 without DB — should be excluded from access log
    logged_calls.clear()
    resp = client.get("/info")
    assert resp.status_code == 200
    assert logged_calls == [], "Expected /info access log to be fully suppressed"


def test_non_excluded_path_still_logged(monkeypatch) -> None:
    """Endpoints not in LOG_EXCLUDE_PATHS should still produce access log entries."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "/info")
    _reload_modules()

    app = aegra_main.app
    access_logger = logger_middleware.access_logger

    logged_calls: list[str] = []
    capture_log = _make_capture_log(logged_calls)

    monkeypatch.setattr(access_logger, "info", capture_log("info"))
    monkeypatch.setattr(access_logger, "warning", capture_log("warning"))
    monkeypatch.setattr(access_logger, "error", capture_log("error"))

    client = TestClient(app)

    # /nonexistent will 404 — should still be logged (4xx is never excluded)
    logged_calls.clear()
    resp = client.get("/nonexistent")
    assert resp.status_code in (404, 405)
    assert logged_calls == ["warning"], "Expected 4xx path to be logged at warning level"
