"""Global pytest configuration and fixtures

This file contains shared fixtures and configuration that are available
to all tests across the test suite.
"""

from unittest.mock import AsyncMock

import pytest

from tests.fixtures.auth import DummyUser
from tests.fixtures.clients import (
    create_test_app,
    install_dummy_user_middleware,
    make_client,
)
from tests.fixtures.database import DummySessionBase, override_get_session_dep
from tests.fixtures.langgraph import (
    FakeAgent,
    FakeGraph,
    FakeSnapshot,
    make_interrupt,
    make_snapshot,
    make_task,
    patch_langgraph_service,
)
from tests.fixtures.session_fixtures import (
    BasicSession,
    RunSession,
    ThreadSession,
    override_session_dependency,
)
from tests.fixtures.test_helpers import (
    DummyRun,
    DummyStoreItem,
    DummyThread,
    make_assistant,
    make_run,
    make_thread,
)

# Export fixtures for use in tests
__all__ = [
    "DummyUser",
    "DummySessionBase",
    "override_get_session_dep",
    "FakeSnapshot",
    "FakeAgent",
    "FakeGraph",
    "make_interrupt",
    "make_snapshot",
    "make_task",
    "patch_langgraph_service",
    "create_test_app",
    "make_client",
    "install_dummy_user_middleware",
    "BasicSession",
    "ThreadSession",
    "RunSession",
    "override_session_dependency",
    "make_assistant",
    "make_thread",
    "make_run",
    "DummyRun",
    "DummyThread",
    "DummyStoreItem",
]


# Add any global fixtures here
@pytest.fixture
def dummy_user():
    """Fixture providing a dummy user for tests"""
    return DummyUser()


@pytest.fixture
def test_user_identity():
    """Fixture providing a test user identity"""
    return "test-user"


@pytest.fixture
def basic_session():
    """Fixture providing a basic mock session"""
    return BasicSession()


@pytest.fixture
def mock_assistant_service():
    """Fixture providing a mocked assistant service"""
    return AsyncMock()


@pytest.fixture
def mock_store():
    """Fixture providing a mocked store"""
    return AsyncMock()


@pytest.fixture
def basic_client(basic_session):
    """Fixture providing a basic test client with mocked session"""
    app = create_test_app(include_runs=False, include_threads=False)
    override_session_dependency(app, BasicSession)
    return make_client(app)


@pytest.fixture
def threads_client():
    """Fixture providing a test client for thread operations"""
    app = create_test_app(include_runs=False, include_threads=True)
    override_session_dependency(app, ThreadSession)
    return make_client(app)


@pytest.fixture
def runs_client():
    """Fixture providing a test client for run operations"""
    app = create_test_app(include_runs=True, include_threads=False)
    override_session_dependency(app, RunSession)
    return make_client(app)
