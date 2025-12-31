"""Tests for CORS middleware configuration in main.py

These tests verify that CORS configuration is properly applied regardless of
whether a custom app is defined, specifically testing the fix for the issue
where expose_headers was not applied in the non-custom-app code path.
"""

import json
import sys

import pytest
from fastapi.middleware.cors import CORSMiddleware


def find_cors_middleware(app):
    """Find the CORSMiddleware in the app's middleware stack."""
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            return middleware
    return None


@pytest.fixture
def isolated_module_reload(tmp_path, monkeypatch):
    """Fixture that provides isolated module reloading with proper cleanup.

    This saves the current module state before the test and restores it after,
    preventing test pollution for subsequent tests.
    """
    monkeypatch.chdir(tmp_path)

    # Save original module state
    original_modules = dict(sys.modules)

    yield tmp_path

    # Restore original module state after test
    # First, remove any new modules that were added
    current_modules = list(sys.modules.keys())
    for mod in current_modules:
        if mod not in original_modules:
            del sys.modules[mod]

    # Then restore any modules that were removed
    for mod, module in original_modules.items():
        if mod not in sys.modules:
            sys.modules[mod] = module


def reload_main_module():
    """Clear agent_server modules from cache and reimport main.

    Note: We preserve certain modules to avoid corrupting global singleton
    state that other tests depend on (observability manager, database/ORM).
    """
    # Modules to preserve (singletons or global state that shouldn't be reset)
    preserve_prefixes = [
        "src.agent_server.observability",
        "src.agent_server.core.database",
        "src.agent_server.core.orm",
        "src.agent_server.services.event_store",
    ]

    modules_to_remove = [
        k
        for k in sys.modules
        if "agent_server" in k
        and not any(k.startswith(prefix) for prefix in preserve_prefixes)
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    from src.agent_server import main

    return main


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_cors_includes_expose_headers(isolated_module_reload):
    """Test that default CORS config includes Content-Location and Location in expose_headers.

    This is critical for LangGraph SDK stream reconnection (reconnectOnMount) to work,
    as the SDK needs to read the Content-Location header from streaming responses.
    """
    tmp_path = isolated_module_reload

    # Create minimal config without http section
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
            }
        )
    )

    main = reload_main_module()

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
async def test_cors_config_without_custom_app_applies_settings(isolated_module_reload):
    """Test that http.cors config is applied even without http.app defined.

    This is the main fix - previously CORS config was only applied when
    a custom app was defined.
    """
    tmp_path = isolated_module_reload

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

    main = reload_main_module()

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
async def test_cors_expose_headers_defaults_when_not_specified(isolated_module_reload):
    """Test that expose_headers defaults to Content-Location and Location when not specified in config."""
    tmp_path = isolated_module_reload

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

    main = reload_main_module()

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
