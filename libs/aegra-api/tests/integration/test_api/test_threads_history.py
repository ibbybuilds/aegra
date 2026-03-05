import json

import pytest
from fastapi.testclient import TestClient

from aegra_api.core.orm import (
    get_session as core_get_session,  # for dependency override
)

# Reuse shared test helpers
from tests.fixtures.clients import create_test_app, make_client
from tests.fixtures.database import DummySessionBase, override_get_session_dep
from tests.fixtures.langgraph import FakeAgent, make_snapshot, patch_langgraph_service
from tests.fixtures.test_helpers import DummyThread


def _thread_row():
    thread = DummyThread(
        thread_id="11111111-1111-1111-1111-111111111111",
        status="idle",
        metadata={"graph_id": "dummy_graph"},
        user_id="test-user",
    )

    # Add ORM-specific attributes
    thread.metadata_json = {"graph_id": "dummy_graph"}
    thread.created_at = None
    thread.updated_at = None

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


@pytest.fixture()
def client() -> TestClient:
    # Build app with threads router only
    app = create_test_app(include_runs=False, include_threads=True)

    # Provide a DummySession that returns a thread row for scalar()
    class Session(DummySessionBase):
        async def scalar(self, _stmt):
            return _thread_row()

    # Override the ORM get_session dependency
    app.dependency_overrides[core_get_session] = override_get_session_dep(Session)

    return make_client(app)


# DummyUser and user injection provided by helpers via create_test_app


# Snapshot creation moved to helpers (make_snapshot)


# No longer needed: app and dependencies are provided by helpers in client() fixture


@pytest.fixture()
def mock_langgraph():
    """
    Patch get_langgraph_service().get_graph(...) so that aget_state_history yields
    deterministic snapshots for both GET and POST tests.
    """

    def _agent_for_config(config):
        c1 = {
            "configurable": {
                "thread_id": config.get("configurable", {}).get("thread_id"),
                "checkpoint_id": "cp_1",
                "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", ""),
            }
        }
        c2 = {
            "configurable": {
                "thread_id": config.get("configurable", {}).get("thread_id"),
                "checkpoint_id": "cp_2",
                "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", ""),
            }
        }
        return FakeAgent(
            [
                make_snapshot({"messages": ["hello"]}, c1, next_nodes=["step_b"]),
                make_snapshot({"messages": ["world"]}, c2, next_nodes=[]),
            ]
        )

    # Use a wrapper agent that builds snapshots using the provided config
    class DynamicFakeAgent(FakeAgent):
        def __init__(self):
            super().__init__(snapshots=[])

        async def aget_state_history(self, config, **kwargs):
            agent = _agent_for_config(config)
            async for s in agent.aget_state_history(config, **kwargs):
                yield s

    with patch_langgraph_service(agent=DynamicFakeAgent()):
        yield


def _ensure_thread(client: TestClient) -> str:
    resp = client.post(
        "/threads",
        json={"metadata": {"purpose": "test-history"}, "initial_state": None},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["thread_id"]


def test_post_history_basic(client: TestClient, mock_langgraph):
    thread_id = _ensure_thread(client)

    # POST history without checkpoint should return two snapshots from fake agent
    payload = {
        "limit": 10,
        "metadata": {"k": "v"},
        "checkpoint": None,
        "subgraphs": False,
        "checkpoint_ns": "",
    }
    resp = client.post(f"/threads/{thread_id}/history", json=payload)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert isinstance(states, list)
    assert len(states) == 2

    # Validate shape of first state
    s0 = states[0]
    assert "values" in s0 and s0["values"]["messages"] == ["hello"]
    assert "checkpoint" in s0 and s0["checkpoint"]["checkpoint_id"] == "cp_1"
    assert s0.get("checkpoint_id") == "cp_1"
    assert s0.get("next") == ["step_b"]


def test_post_history_with_checkpoint_ns(client: TestClient, mock_langgraph):
    thread_id = _ensure_thread(client)

    payload = {
        "limit": 10,
        "checkpoint": {"checkpoint_ns": "nsA"},
        "subgraphs": True,
    }
    resp = client.post(f"/threads/{thread_id}/history", json=payload)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert len(states) == 2
    for s in states:
        assert s["checkpoint"]["checkpoint_ns"] == "nsA"


def test_get_history_basic(client: TestClient, mock_langgraph):
    thread_id = _ensure_thread(client)

    # GET history with default params
    resp = client.get(f"/threads/{thread_id}/history")
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert isinstance(states, list)
    assert len(states) == 2

    # GET history with metadata as JSON string and checkpoint_ns
    resp = client.get(
        f"/threads/{thread_id}/history",
        params={
            "limit": 10,
            "metadata": json.dumps({"foo": "bar"}),
            "checkpoint_ns": "nsB",
            "subgraphs": "true",
        },
    )
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert len(states) == 2
    for s in states:
        assert s["checkpoint"]["checkpoint_ns"] == "nsB"


def test_history_invalid_limit(client: TestClient, mock_langgraph):
    thread_id = _ensure_thread(client)

    # POST invalid limit type
    resp = client.post(f"/threads/{thread_id}/history", json={"limit": "ten"})
    assert resp.status_code == 422

    # GET invalid metadata JSON
    resp = client.get(f"/threads/{thread_id}/history", params={"metadata": "{not-json"})
    assert resp.status_code == 422


def test_post_history_include_values_true_returns_values(client: TestClient, mock_langgraph):
    """When include_values is true (default), values are present in the response."""
    thread_id = _ensure_thread(client)

    resp = client.post(f"/threads/{thread_id}/history", json={"limit": 10, "include_values": True})
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) == 2
    assert states[0]["values"]["messages"] == ["hello"]
    assert states[1]["values"]["messages"] == ["world"]


def test_post_history_include_values_false_strips_values(client: TestClient, mock_langgraph):
    """When include_values is false, values are empty dicts but all metadata is preserved."""
    thread_id = _ensure_thread(client)

    resp = client.post(f"/threads/{thread_id}/history", json={"limit": 10, "include_values": False})
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) == 2

    for state in states:
        # Values should be stripped (empty dict)
        assert state["values"] == {}

        # All checkpoint metadata must still be present
        assert "checkpoint" in state
        assert state["checkpoint"]["checkpoint_id"] is not None
        assert "parent_checkpoint" in state
        assert "metadata" in state
        assert "next" in state
        assert "tasks" in state
        assert "created_at" in state


def test_post_history_include_values_default_is_true(client: TestClient, mock_langgraph):
    """When include_values is omitted, it defaults to true (backward compatible)."""
    thread_id = _ensure_thread(client)

    # Omit include_values entirely
    resp = client.post(f"/threads/{thread_id}/history", json={"limit": 10})
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) == 2
    # Values should be present (default behavior unchanged)
    assert states[0]["values"]["messages"] == ["hello"]


def test_get_history_include_values_false(client: TestClient, mock_langgraph):
    """GET variant also supports include_values=false."""
    thread_id = _ensure_thread(client)

    resp = client.get(f"/threads/{thread_id}/history", params={"include_values": "false"})
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) == 2

    for state in states:
        assert state["values"] == {}
        assert state["checkpoint"]["checkpoint_id"] is not None


def test_post_history_include_values_false_preserves_checkpoint_structure(client: TestClient, mock_langgraph):
    """Lightweight history preserves the full checkpoint structure needed for branching."""
    thread_id = _ensure_thread(client)

    resp = client.post(f"/threads/{thread_id}/history", json={"limit": 10, "include_values": False})
    assert resp.status_code == 200
    states = resp.json()

    # First state should have checkpoint with ID
    assert states[0]["checkpoint"]["checkpoint_id"] == "cp_1"
    assert states[0]["checkpoint"]["thread_id"] == thread_id

    # Second state should have checkpoint with ID
    assert states[1]["checkpoint"]["checkpoint_id"] == "cp_2"
    assert states[1]["checkpoint"]["thread_id"] == thread_id

    # Next nodes should be preserved
    assert states[0]["next"] == ["step_b"]
    assert states[1]["next"] == []
