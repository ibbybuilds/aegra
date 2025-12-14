"""Unit tests for route merger"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from src.agent_server.core.route_merger import (
    merge_exception_handlers,
    merge_lifespans,
    merge_routes,
    update_openapi_spec,
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


@pytest.fixture
def shadowable_routes():
    """Create shadowable routes"""
    return [Route("/", dummy_handler, methods=["GET"])]


@pytest.fixture
def unshadowable_routes():
    """Create unshadowable routes"""
    return [Route("/health", dummy_handler, methods=["GET"])]


@pytest.fixture
def protected_mount():
    """Create protected mount"""
    return Mount("/api", routes=[Route("/test", dummy_handler, methods=["GET"])])


def test_merge_routes(
    user_app, shadowable_routes, unshadowable_routes, protected_mount
):
    """Test merging routes with correct priority"""
    merged_app = merge_routes(
        user_app=user_app,
        unshadowable_routes=unshadowable_routes,
        shadowable_routes=shadowable_routes,
        protected_mount=protected_mount,
    )

    assert merged_app is user_app
    routes = list(merged_app.routes)

    # FastAPI adds default routes (/docs, /openapi.json, etc.) which come first
    # Check route order: FastAPI defaults -> unshadowable -> custom -> shadowable -> protected
    route_paths = [r.path for r in routes if hasattr(r, "path")]

    # Find positions of our routes
    health_idx = route_paths.index("/health")
    custom_idx = route_paths.index("/custom")
    root_idx = route_paths.index("/")

    # Check priority order: unshadowable comes before custom, custom before shadowable
    assert health_idx < custom_idx < root_idx

    # Protected mount should be last
    assert isinstance(routes[-1], Mount)


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


def test_update_openapi_spec_fastapi(user_app):
    """Test updating OpenAPI spec for FastAPI app"""
    # Should not raise
    update_openapi_spec(user_app)


def test_update_openapi_spec_starlette():
    """Test updating OpenAPI spec for Starlette app"""
    app = Starlette()
    # Should not raise
    update_openapi_spec(app)
