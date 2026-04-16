import importlib
import json
import sys
from collections.abc import Callable

from starlette.testclient import TestClient


def reload_logging_modules() -> None:
    """
    Helper to reload settings and logging setup modules safely.
    Uses sys.modules lookup to avoid ImportError if alias is stale.
    """
    # 1. Ensure modules are imported

    # 2. Reload explicitly via sys.modules
    if "aegra_api.settings" in sys.modules:
        importlib.reload(sys.modules["aegra_api.settings"])

    if "aegra_api.utils.setup_logging" in sys.modules:
        importlib.reload(sys.modules["aegra_api.utils.setup_logging"])

    if "aegra_api.middleware.logger_middleware" in sys.modules:
        importlib.reload(sys.modules["aegra_api.middleware.logger_middleware"])


def test_structlog_middleware_handles_exceptions_and_success():
    """Test that the middleware correctly logs requests and handles exceptions."""
    from aegra_api.middleware.logger_middleware import StructLogMiddleware

    async def asgi_ok(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"status":"ok"}'})

    async def asgi_boom(scope, receive, send):
        raise RuntimeError("boom")

    client_ok = TestClient(StructLogMiddleware(asgi_ok))
    client_boom = TestClient(StructLogMiddleware(asgi_boom), raise_server_exceptions=False)

    r = client_ok.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

    r2 = client_boom.get("/")
    assert r2.status_code == 500


def test_log_exclude_paths_skips_access_log_for_successful_responses(monkeypatch):
    """Excluded paths with 2xx responses should not produce access log entries."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "/health,/metrics")
    reload_logging_modules()

    from aegra_api.middleware.logger_middleware import StructLogMiddleware, access_logger

    logged_calls: list[str] = []

    def capture_log(method_name: str) -> Callable[..., None]:
        def _log(msg: str, *args: object, **kwargs: object) -> None:
            logged_calls.append(method_name)

        return _log

    monkeypatch.setattr(access_logger, "info", capture_log("info"))
    monkeypatch.setattr(access_logger, "warning", capture_log("warning"))
    monkeypatch.setattr(access_logger, "error", capture_log("error"))

    async def asgi_ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    client = TestClient(StructLogMiddleware(asgi_ok))

    # Excluded paths — should NOT log
    logged_calls.clear()
    client.get("/health")
    assert logged_calls == [], "Expected /health to be excluded from access log"

    logged_calls.clear()
    client.get("/health/ready")
    assert logged_calls == [], "Expected /health/ready to be excluded (prefix match)"

    logged_calls.clear()
    client.get("/metrics")
    assert logged_calls == [], "Expected /metrics to be excluded from access log"

    # Non-excluded path — should log
    logged_calls.clear()
    client.get("/api/threads")
    assert logged_calls == ["info"], "Expected /api/threads to be logged"


def test_log_exclude_paths_still_logs_errors_for_excluded_paths(monkeypatch):
    """4xx/5xx responses on excluded paths should still be logged."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "/health")
    reload_logging_modules()

    from aegra_api.middleware.logger_middleware import StructLogMiddleware, access_logger

    logged_calls: list[str] = []

    def capture_log(method_name: str) -> Callable[..., None]:
        def _log(msg: str, *args: object, **kwargs: object) -> None:
            logged_calls.append(method_name)

        return _log

    monkeypatch.setattr(access_logger, "info", capture_log("info"))
    monkeypatch.setattr(access_logger, "warning", capture_log("warning"))
    monkeypatch.setattr(access_logger, "error", capture_log("error"))

    async def asgi_404(scope, receive, send):
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"not found"})

    async def asgi_500(scope, receive, send):
        await send({"type": "http.response.start", "status": 500, "headers": []})
        await send({"type": "http.response.body", "body": b"error"})

    # 404 on excluded path — should still log as warning
    logged_calls.clear()
    TestClient(StructLogMiddleware(asgi_404)).get("/health")
    assert logged_calls == ["warning"], "Expected 404 on /health to be logged as warning"

    # 500 on excluded path — should still log as error
    logged_calls.clear()
    TestClient(StructLogMiddleware(asgi_500)).get("/health")
    assert logged_calls == ["error"], "Expected 500 on /health to be logged as error"


def test_log_exclude_paths_empty_logs_everything(monkeypatch):
    """When LOG_EXCLUDE_PATHS is empty (default), all paths are logged."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "")
    reload_logging_modules()

    from aegra_api.middleware.logger_middleware import StructLogMiddleware, access_logger

    logged_calls: list[str] = []

    monkeypatch.setattr(access_logger, "info", lambda *a, **kw: logged_calls.append("info"))
    monkeypatch.setattr(access_logger, "warning", lambda *a, **kw: logged_calls.append("warning"))
    monkeypatch.setattr(access_logger, "error", lambda *a, **kw: logged_calls.append("error"))

    async def asgi_ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    client = TestClient(StructLogMiddleware(asgi_ok))

    logged_calls.clear()
    client.get("/health")
    assert logged_calls == ["info"], "Expected /health to be logged when no exclusions configured"


def test_log_exclude_paths_parsing(monkeypatch):
    """Test that LOG_EXCLUDE_PATHS is parsed correctly into a tuple."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", " /health , /ok ,, /metrics ")
    reload_logging_modules()

    from aegra_api.settings import AppSettings

    s = AppSettings()
    assert s.log_exclude_paths == ("/health", "/ok", "/metrics")


def test_log_exclude_paths_parsing_empty(monkeypatch):
    """Empty LOG_EXCLUDE_PATHS returns empty tuple."""
    monkeypatch.setenv("LOG_EXCLUDE_PATHS", "")
    reload_logging_modules()

    from aegra_api.settings import AppSettings

    s = AppSettings()
    assert s.log_exclude_paths == ()


def test_get_logging_config_and_setup(monkeypatch):
    import structlog

    # --- 1. TEST LOCAL MODE ---
    monkeypatch.setenv("ENV_MODE", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    reload_logging_modules()

    from aegra_api.utils.setup_logging import get_logging_config, setup_logging

    cfg = get_logging_config()
    # The renderer is the last entry in the "processors" list
    renderer = cfg["formatters"]["default"]["processors"][-1]
    assert "ConsoleRenderer" in renderer.__class__.__name__

    # --- 2. TEST PRODUCTION MODE ---
    monkeypatch.setenv("ENV_MODE", "PRODUCTION")

    reload_logging_modules()

    # Re-import to get fresh config logic
    from aegra_api.utils.setup_logging import get_logging_config

    cfg2 = get_logging_config()
    renderer2 = cfg2["formatters"]["default"]["processors"][-1]
    assert "JSONRenderer" in renderer2.__class__.__name__

    setup_logging()
    assert hasattr(structlog, "get_logger")


def test_main_app_middleware_order():
    from aegra_api.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert "StructLogMiddleware" in names
    assert "CorrelationIdMiddleware" in names


def test_structured_fields_work(monkeypatch, caplog, capsys):
    import structlog

    monkeypatch.setenv("ENV_MODE", "PRODUCTION")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    reload_logging_modules()

    from aegra_api.utils.setup_logging import setup_logging

    setup_logging()

    logger = structlog.get_logger("test_structured")
    logger.info("my_event", trace_id="tx-123", user="alice", count=5)

    out = capsys.readouterr().out.strip()
    assert out, "No output captured from logging StreamHandler"

    first_line = next((line for line in out.splitlines() if line.strip()), None)
    assert first_line is not None
    parsed = json.loads(first_line)
    assert parsed.get("event") == "my_event"
    assert parsed.get("trace_id") == "tx-123"
