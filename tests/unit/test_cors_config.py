"""Tests for CORS middleware configuration in main.py

These tests verify that CORS configuration is properly applied regardless of
whether a custom app is defined, specifically testing the fix for the issue
where expose_headers was not applied in the non-custom-app code path.
"""

import json

import pytest
from fastapi.middleware.cors import CORSMiddleware


def find_cors_middleware(app):
    """Find the CORSMiddleware in the app's middleware stack."""
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            return middleware
    return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_cors_includes_expose_headers(tmp_path, monkeypatch):
    """Test that default CORS config includes Content-Location and Location in expose_headers.

    This is critical for LangGraph SDK stream reconnection (reconnectOnMount) to work,
    as the SDK needs to read the Content-Location header from streaming responses.
    """
    monkeypatch.chdir(tmp_path)

    # Create minimal config without http section
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
            }
        )
    )

    # Clear the module cache to force reload with new config
    import sys

    modules_to_remove = [k for k in sys.modules.keys() if "agent_server" in k]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Import main to trigger app creation with our config
    from src.agent_server import main

    cors_middleware = find_cors_middleware(main.app)
    assert cors_middleware is not None, "CORS middleware should be present"

    # Check that expose_headers includes the required headers
    expose_headers = cors_middleware.kwargs.get("expose_headers", [])
    assert "Content-Location" in expose_headers, (
        "Content-Location should be in expose_headers by default"
    )
    assert "Location" in expose_headers, (
        "Location should be in expose_headers by default"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cors_config_without_custom_app_applies_settings(tmp_path, monkeypatch):
    """Test that http.cors config is applied even without http.app defined.

    This is the main fix - previously CORS config was only applied when
    a custom app was defined.
    """
    monkeypatch.chdir(tmp_path)

    # Create config with cors but no custom app
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {
                    "cors": {
                        "allow_origins": ["https://myapp.example.com"],
                        "expose_headers": [
                            "Content-Location",
                            "Location",
                            "X-Request-ID",
                        ],
                        "max_age": 3600,
                    },
                },
            }
        )
    )

    # Clear the module cache to force reload with new config
    import sys

    modules_to_remove = [k for k in sys.modules.keys() if "agent_server" in k]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Import main to trigger app creation with our config
    from src.agent_server import main

    cors_middleware = find_cors_middleware(main.app)
    assert cors_middleware is not None, "CORS middleware should be present"

    # Verify custom settings were applied
    assert cors_middleware.kwargs.get("allow_origins") == [
        "https://myapp.example.com"
    ], "Custom allow_origins should be applied"

    expose_headers = cors_middleware.kwargs.get("expose_headers", [])
    assert "X-Request-ID" in expose_headers, "Custom expose_headers should be applied"
    assert "Content-Location" in expose_headers
    assert "Location" in expose_headers

    assert cors_middleware.kwargs.get("max_age") == 3600, (
        "Custom max_age should be applied"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cors_expose_headers_defaults_when_not_specified(tmp_path, monkeypatch):
    """Test that expose_headers defaults to Content-Location and Location when not specified in config."""
    monkeypatch.chdir(tmp_path)

    # Create config with cors but without expose_headers
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {
                    "cors": {
                        "allow_origins": ["*"],
                        # Note: expose_headers is NOT specified
                    },
                },
            }
        )
    )

    # Clear the module cache to force reload with new config
    import sys

    modules_to_remove = [k for k in sys.modules.keys() if "agent_server" in k]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Import main to trigger app creation with our config
    from src.agent_server import main

    cors_middleware = find_cors_middleware(main.app)
    assert cors_middleware is not None, "CORS middleware should be present"

    # Should have default expose_headers even though cors config exists but
    # doesn't specify expose_headers
    expose_headers = cors_middleware.kwargs.get("expose_headers", [])
    assert "Content-Location" in expose_headers, (
        "Content-Location should default when not specified in cors config"
    )
    assert "Location" in expose_headers, (
        "Location should default when not specified in cors config"
    )
