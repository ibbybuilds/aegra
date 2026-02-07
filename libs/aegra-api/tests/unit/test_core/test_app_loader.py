"""Unit tests for custom app loader"""

import pytest
from fastapi import FastAPI

from aegra_api.core.app_loader import load_custom_app


def test_load_custom_app_from_file(tmp_path):
    """Test loading custom app from file path"""
    # Create a temporary Python file with a FastAPI app
    app_file = tmp_path / "custom_app.py"
    app_file.write_text(
        """
from fastapi import FastAPI

app = FastAPI()

@app.get("/custom")
async def custom():
    return {"message": "custom"}
"""
    )

    # Load the app
    loaded_app = load_custom_app(f"{app_file}:app")

    assert isinstance(loaded_app, FastAPI)
    # FastAPI automatically adds routes for /docs, /openapi.json, /redoc, etc.
    # So we check that our custom route exists rather than exact count
    route_paths = [r.path for r in loaded_app.routes if hasattr(r, "path")]
    assert "/custom" in route_paths


def test_load_custom_app_from_file_starlette(tmp_path):
    """Test that Starlette apps are rejected (only FastAPI allowed)"""
    # Create a temporary Python file with a Starlette app
    app_file = tmp_path / "custom_starlette.py"
    app_file.write_text(
        """
from starlette.applications import Starlette
from starlette.routing import Route

async def handler(request):
    return {"message": "custom"}

app = Starlette(routes=[Route("/custom", handler)])
"""
    )

    # Starlette apps should be rejected - only FastAPI is allowed
    with pytest.raises(TypeError, match="not a FastAPI application"):
        load_custom_app(f"{app_file}:app")


def test_load_custom_app_invalid_format():
    """Test loading app with invalid format"""
    with pytest.raises(ValueError, match="Invalid app import path format"):
        load_custom_app("invalid_path_without_colon")


def test_load_custom_app_file_not_found():
    """Test loading app from non-existent file"""
    with pytest.raises(FileNotFoundError):
        load_custom_app("./nonexistent_file.py:app")


def test_load_custom_app_missing_variable(tmp_path):
    """Test loading app when variable doesn't exist"""
    app_file = tmp_path / "no_app.py"
    app_file.write_text("x = 1")

    with pytest.raises(AttributeError, match="App 'app' not found"):
        load_custom_app(f"{app_file}:app")


def test_load_custom_app_not_starlette(tmp_path):
    """Test loading app when variable is not a FastAPI app"""
    app_file = tmp_path / "not_app.py"
    app_file.write_text("app = 'not an app'")

    with pytest.raises(TypeError, match="not a FastAPI application"):
        load_custom_app(f"{app_file}:app")


def test_load_custom_app_module_import():
    """Test loading app from module path (if module exists)"""
    # This test would require a real module, so we'll skip it or mock it
    # For now, we'll test that it raises ImportError for non-existent module
    with pytest.raises(ImportError):
        load_custom_app("nonexistent.module:app")
