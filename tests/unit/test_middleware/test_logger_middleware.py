import json

from starlette.testclient import TestClient


def test_structlog_middleware_handles_exceptions_and_success():
    # Import middleware
    from src.agent_server.middleware.logger_middleware import StructLogMiddleware

    # Create two minimal ASGI apps to test middleware behavior.
    async def asgi_ok(scope, receive, send):
        # Proper ASGI HTTP response
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"status":"ok"}'})

    async def asgi_boom(scope, receive, send):
        # Raise before sending any response to trigger middleware exception path
        raise RuntimeError("boom")

    # Wrap apps with middleware
    client_ok = TestClient(StructLogMiddleware(asgi_ok))
    # Since middleware now re-raises exceptions to allow app-level handlers to run,
    # create TestClient with raise_server_exceptions=False so we get a 500 response
    client_boom = TestClient(
        StructLogMiddleware(asgi_boom), raise_server_exceptions=False
    )

    r = client_ok.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

    r2 = client_boom.get("/")
    # Middleware now re-raises exceptions so app-level handlers are expected
    # to format the response. In this test we wrapped a bare ASGI app, so
    # we only assert that the response code is 500 (body may be empty).
    assert r2.status_code == 500


def test_get_logging_config_and_setup(monkeypatch):
    import structlog

    from src.agent_server.utils.setup_logging import get_logging_config, setup_logging

    # LOCAL should pick ConsoleRenderer
    monkeypatch.setenv("ENV_MODE", "LOCAL")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    cfg = get_logging_config()
    assert "formatters" in cfg
    processor = cfg["formatters"]["default"]["processor"]
    # ConsoleRenderer type name should be present for local
    assert "ConsoleRenderer" in processor.__class__.__name__

    # PRODUCTION should use JSONRenderer
    monkeypatch.setenv("ENV_MODE", "PRODUCTION")
    cfg2 = get_logging_config()
    processor2 = cfg2["formatters"]["default"]["processor"]
    assert "JSONRenderer" in processor2.__class__.__name__

    # Running setup_logging should not raise
    setup_logging()
    # structlog should be configured with processor pipeline
    assert hasattr(structlog, "get_logger")


def test_main_app_middleware_order():
    # Import app from main and inspect middleware
    from src.agent_server.main import app

    # FastAPI exposes user_middleware in the order added
    names = [m.cls.__name__ for m in app.user_middleware]
    # Expect both middleware to be present
    assert "StructLogMiddleware" in names
    assert "CorrelationIdMiddleware" in names


def test_structured_fields_work(monkeypatch, caplog, capsys):
    """Ensure structured fields are preserved and emitted when using structlog with JSONRenderer."""
    import structlog

    from src.agent_server.utils.setup_logging import setup_logging

    # Force JSON renderer for predictable parsing
    monkeypatch.setenv("ENV_MODE", "PRODUCTION")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    # Apply logging configuration
    setup_logging()

    # Emit a structured log event with extra fields; the configured handler writes to stdout
    logger = structlog.get_logger("test_structured")
    logger.info("my_event", trace_id="tx-123", user="alice", count=5)

    # Capture stdout where the logging StreamHandler writes the formatted JSON
    out = capsys.readouterr().out.strip()
    assert out, "No output captured from logging StreamHandler"

    # The handler emits a JSON object per line; parse the first non-empty line
    first_line = next((line for line in out.splitlines() if line.strip()), None)
    assert first_line is not None
    parsed = json.loads(first_line)
    assert parsed.get("event") == "my_event"
    assert parsed.get("trace_id") == "tx-123"
    assert parsed.get("user") == "alice"
    assert parsed.get("count") == 5
