"""Integration tests for threads CRUD operations"""

import pytest
from fastapi.testclient import TestClient

from aegra.agent_server.core.orm import get_session as core_get_session
from tests.fixtures.clients import create_test_app, make_client
from tests.fixtures.database import DummySessionBase, override_get_session_dep
from tests.fixtures.session_fixtures import BasicSession, override_session_dependency
from tests.fixtures.test_helpers import DummyRun, DummyThread


def _thread_row(
    thread_id="test-thread-123", status="idle", metadata=None, user_id="test-user"
):
    """Create a mock thread ORM object"""
    thread = DummyThread(thread_id, status, metadata, user_id)

    # Add ORM-specific attributes
    thread.metadata_json = metadata or {}

    class _Col:
        def __init__(self, name):
            self.name = name

    class _T:
        columns = [
            _Col("thread_id"),
            _Col("status"),
            _Col("metadata"),
            _Col("user_id"),
            _Col("created_at"),
            _Col("updated_at"),
        ]

    thread.__table__ = _T()
    return thread


def _run_row(
    run_id="test-run-123",
    thread_id="test-thread-123",
    status="running",
    user_id="test-user",
):
    """Create a mock run ORM object"""
    return DummyRun(run_id, thread_id, status, user_id)


class TestCreateThread:
    """Test POST /threads endpoint"""

    @pytest.fixture
    def client(self) -> TestClient:
        app = create_test_app(include_runs=False, include_threads=True)
        override_session_dependency(app, BasicSession)
        return make_client(app)

    def test_create_thread_basic(self, client):
        """Test creating a thread with basic metadata"""
        resp = client.post(
            "/threads",
            json={"metadata": {"purpose": "testing"}, "initial_state": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert data["status"] == "idle"
        assert data["metadata"]["purpose"] == "testing"
        assert data["metadata"]["owner"] == "test-user"
        assert data["metadata"]["assistant_id"] is None
        assert data["metadata"]["graph_id"] is None

    def test_create_thread_empty_request(self, client):
        """Test creating a thread with empty request body"""
        resp = client.post("/threads", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert "owner" in data["metadata"]

    def test_create_thread_with_complex_metadata(self, client):
        """Test creating a thread with complex nested metadata"""
        resp = client.post(
            "/threads",
            json={
                "metadata": {
                    "tags": ["urgent", "production"],
                    "context": {"user_type": "premium", "tier": 3},
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["tags"] == ["urgent", "production"]
        assert data["metadata"]["context"]["tier"] == 3


class TestListThreads:
    """Test GET /threads endpoint"""

    def test_list_threads_with_results(self):
        """Test listing threads when user has threads"""
        app = create_test_app(include_runs=False, include_threads=True)

        threads = [
            _thread_row("thread-1", metadata={"name": "First"}),
            _thread_row("thread-2", metadata={"name": "Second"}),
            _thread_row("thread-3", metadata={"name": "Third"}),
        ]

        class Session(DummySessionBase):
            async def scalars(self, _stmt):
                class Result:
                    def all(self):
                        return threads

                return Result()

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert "threads" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["threads"]) == 3

    def test_list_threads_empty(self):
        """Test listing threads when user has no threads"""
        app = create_test_app(include_runs=False, include_threads=True)

        class Session(DummySessionBase):
            async def scalars(self, _stmt):
                class Result:
                    def all(self):
                        return []

                return Result()

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["threads"] == []


class TestGetThread:
    """Test GET /threads/{thread_id} endpoint"""

    def test_get_thread_success(self):
        """Test getting an existing thread"""
        app = create_test_app(include_runs=False, include_threads=True)

        thread = _thread_row("test-123", metadata={"purpose": "testing"})

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return thread

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads/test-123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "test-123"
        assert data["metadata"]["purpose"] == "testing"

    def test_get_thread_not_found(self):
        """Test getting a non-existent thread"""
        app = create_test_app(include_runs=False, include_threads=True)

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return None

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestDeleteThread:
    """Test DELETE /threads/{thread_id} endpoint"""

    def test_delete_thread_not_found(self):
        """Test deleting a non-existent thread"""
        app = create_test_app(include_runs=False, include_threads=True)

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return None

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.delete("/threads/nonexistent")
        assert resp.status_code == 404

    def test_delete_thread_no_active_runs(self):
        """Test deleting a thread with no active runs"""
        app = create_test_app(include_runs=False, include_threads=True)

        thread = _thread_row("test-123")

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return thread

            async def scalars(self, _stmt):
                class Result:
                    def all(self):
                        return []

                return Result()

            async def delete(self, obj):
                pass

            async def commit(self):
                pass

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.delete("/threads/test-123")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestSearchThreads:
    """Test POST /threads/search endpoint"""

    @pytest.fixture
    def client(self) -> TestClient:
        app = create_test_app(include_runs=False, include_threads=True)

        threads = [
            _thread_row(
                "thread-1", status="idle", metadata={"env": "prod", "team": "alpha"}
            ),
            _thread_row(
                "thread-2", status="active", metadata={"env": "dev", "team": "beta"}
            ),
            _thread_row(
                "thread-3", status="idle", metadata={"env": "prod", "team": "beta"}
            ),
        ]

        from tests.fixtures.session_fixtures import ThreadSession

        override_session_dependency(app, ThreadSession, threads=threads)
        return make_client(app)

    def test_search_threads_no_filters(self, client):
        """Test searching without any filters"""
        resp = client.post("/threads/search", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_search_threads_with_status(self, client):
        """Test searching with status filter"""
        resp = client.post("/threads/search", json={"status": "idle"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_threads_with_metadata(self, client):
        """Test searching with metadata filter"""
        resp = client.post(
            "/threads/search",
            json={"metadata": {"env": "prod"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_threads_with_pagination(self, client):
        """Test searching with offset and limit"""
        resp = client.post(
            "/threads/search",
            json={"offset": 0, "limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_threads_combined_filters(self, client):
        """Test searching with multiple filters combined"""
        resp = client.post(
            "/threads/search",
            json={
                "status": "idle",
                "metadata": {"env": "prod"},
                "offset": 0,
                "limit": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestThreadStateCheckpoint:
    """Test GET /threads/{thread_id}/state/{checkpoint_id} endpoint"""

    def test_get_state_thread_not_found(self):
        """Test getting state when thread doesn't exist"""
        app = create_test_app(include_runs=False, include_threads=True)

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return None

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads/nonexistent/state/checkpoint-1")
        assert resp.status_code == 404

    def test_get_state_no_graph_id(self):
        """Test getting state when thread has no associated graph"""
        app = create_test_app(include_runs=False, include_threads=True)

        thread = _thread_row("test-123", metadata={})

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return thread

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.get("/threads/test-123/state/checkpoint-1")
        assert resp.status_code == 404
        assert "no associated graph" in resp.json()["detail"]

    def test_get_state_with_subgraphs_param(self):
        """Test getting state with subgraphs query parameter"""
        app = create_test_app(include_runs=False, include_threads=True)

        thread = _thread_row("test-123", metadata={})

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return thread

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        # Should fail because no graph_id, but tests that param is accepted
        resp = client.get("/threads/test-123/state/checkpoint-1?subgraphs=true")
        assert resp.status_code == 404


class TestThreadStateCheckpointPost:
    """Test POST /threads/{thread_id}/state/checkpoint endpoint"""

    def test_post_checkpoint_thread_not_found(self):
        """Test POST checkpoint when thread doesn't exist"""
        app = create_test_app(include_runs=False, include_threads=True)

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return None

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.post(
            "/threads/nonexistent/state/checkpoint",
            json={"checkpoint": {"checkpoint_id": "cp-1"}, "subgraphs": False},
        )
        assert resp.status_code == 404

    def test_post_checkpoint_no_graph_id(self):
        """Test POST checkpoint when thread has no graph"""
        app = create_test_app(include_runs=False, include_threads=True)

        thread = _thread_row("test-123", metadata={})

        class Session(DummySessionBase):
            async def scalar(self, _stmt):
                return thread

        app.dependency_overrides[core_get_session] = override_get_session_dep(Session)
        client = make_client(app)

        resp = client.post(
            "/threads/test-123/state/checkpoint",
            json={"checkpoint": {"checkpoint_id": "cp-1"}, "subgraphs": True},
        )
        assert resp.status_code == 404
