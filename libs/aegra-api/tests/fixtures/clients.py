"""Test client fixtures"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def install_dummy_user_middleware(app: FastAPI) -> None:
    """Install middleware that injects a dummy user for testing"""
    from tests.fixtures.auth import DummyUser

    @app.middleware("http")
    async def inject_dummy_user(request, call_next):
        request.scope["user"] = DummyUser()
        return await call_next(request)


def create_test_app(include_runs: bool = True, include_threads: bool = True) -> FastAPI:
    """Build a FastAPI app with routers mounted and dummy user middleware

    Dependency overrides must be installed by the caller to control DB behavior.
    """
    app = FastAPI()
    install_dummy_user_middleware(app)

    if include_threads:
        from aegra_api.api import threads as threads_module

        app.include_router(threads_module.router)

    if include_runs:
        from aegra_api.api import runs as runs_module

        app.include_router(runs_module.router)

    return app


def make_client(app: FastAPI) -> TestClient:
    """Create a test client for the given app"""
    return TestClient(app)
