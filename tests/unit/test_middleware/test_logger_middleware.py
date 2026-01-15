import importlib
import json
import sys

from starlette.testclient import TestClient


def reload_logging_modules():
    """
    Helper to reload settings and logging setup modules safely.
    Uses sys.modules lookup to avoid ImportError if alias is stale.
    """
    # 1. Ensure modules are imported

    # 2. Reload explicitly via sys.modules
    if "src.agent_server.settings" in sys.modules:
        importlib.reload(sys.modules["src.agent_server.settings"])

    if "src.agent_server.utils.setup_logging" in sys.modules:
        importlib.reload(sys.modules["src.agent_server.utils.setup_logging"])


def test_structlog_middleware_handles_exceptions_and_success():
    """Test that the middleware correctly logs requests and handles exceptions."""
    from src.agent_server.middleware.logger_middleware import StructLogMiddleware

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
    client_boom = TestClient(
        StructLogMiddleware(asgi_boom), raise_server_exceptions=False
    )

    r = client_ok.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

    r2 = client_boom.get("/")
    assert r2.status_code == 500


def test_get_logging_config_and_setup(monkeypatch):
    import structlog

    # --- 1. TEST LOCAL MODE ---
    monkeypatch.setenv("ENV_MODE", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    reload_logging_modules()

    from src.agent_server.utils.setup_logging import get_logging_config, setup_logging

    cfg = get_logging_config()
    processor = cfg["formatters"]["default"]["processor"]
    assert "ConsoleRenderer" in processor.__class__.__name__

    # --- 2. TEST PRODUCTION MODE ---
    monkeypatch.setenv("ENV_MODE", "PRODUCTION")

    reload_logging_modules()

    # Re-import to get fresh config logic
    from src.agent_server.utils.setup_logging import get_logging_config

    cfg2 = get_logging_config()
    processor2 = cfg2["formatters"]["default"]["processor"]
    assert "JSONRenderer" in processor2.__class__.__name__

    setup_logging()
    assert hasattr(structlog, "get_logger")


def test_main_app_middleware_order():
    from src.agent_server.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert "StructLogMiddleware" in names
    assert "CorrelationIdMiddleware" in names


def test_structured_fields_work(monkeypatch, caplog, capsys):
    import structlog

    monkeypatch.setenv("ENV_MODE", "PRODUCTION")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    reload_logging_modules()

    from src.agent_server.utils.setup_logging import setup_logging

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
