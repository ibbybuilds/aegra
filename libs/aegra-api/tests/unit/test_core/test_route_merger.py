"""Unit tests for route merger"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from aegra_api.core.route_merger import (
    merge_exception_handlers,
    merge_lifespans,
)


async def dummy_handler(request):
    """Dummy handler for testing"""
    return {"test": "data"}


@pytest.fixture
def user_app():
    """Create a test user FastAPI app"""
    app = FastAPI()
    app.add_api_route("/custom", dummy_handler, methods=["GET"])
    return app


# Note: merge_routes() has been removed - routes are now merged via include_router()
# Route merging is now handled directly in main.py using FastAPI's include_router()


def test_merge_lifespans(user_app):
    """Test merging lifespans"""

    @asynccontextmanager
    async def core_lifespan(app):
        yield

    merged_app = merge_lifespans(user_app, core_lifespan)

    assert merged_app is user_app
    assert merged_app.router.lifespan_context is not None


def test_merge_lifespans_with_user_lifespan(user_app):
    """Test merging lifespans when user has lifespan"""

    @asynccontextmanager
    async def core_lifespan(app):
        yield

    @asynccontextmanager
    async def user_lifespan(app):
        yield

    user_app.router.lifespan_context = user_lifespan
    merged_app = merge_lifespans(user_app, core_lifespan)

    assert merged_app is user_app
    assert merged_app.router.lifespan_context is not None


def test_merge_lifespans_rejects_startup_shutdown(user_app):
    """Test that merge_lifespans rejects deprecated startup/shutdown handlers"""
    user_app.router.on_startup = [lambda: None]

    @asynccontextmanager
    async def core_lifespan(app):
        yield

    with pytest.raises(ValueError, match="Cannot merge lifespans with on_startup"):
        merge_lifespans(user_app, core_lifespan)


def test_merge_exception_handlers(user_app):
    """Test merging exception handlers"""

    async def core_handler(request, exc):
        return {"error": "core"}

    core_handlers = {ValueError: core_handler}
    merged_app = merge_exception_handlers(user_app, core_handlers)

    assert merged_app is user_app
    assert ValueError in merged_app.exception_handlers


def test_merge_exception_handlers_user_override(user_app):
    """Test that user exception handlers take precedence"""

    async def core_handler(request, exc):
        return {"error": "core"}

    async def user_handler(request, exc):
        return {"error": "user"}

    user_app.exception_handlers[ValueError] = user_handler
    core_handlers = {ValueError: core_handler}
    merged_app = merge_exception_handlers(user_app, core_handlers)

    assert merged_app is user_app
    # User handler should remain
    assert merged_app.exception_handlers[ValueError] is user_handler


# Note: update_openapi_spec() has been removed - FastAPI automatically handles OpenAPI
# when using include_router(), so no manual spec update is needed
