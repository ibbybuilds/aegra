"""Integration tests for authorization handlers with real auth instances"""

import json

import pytest
from fastapi import HTTPException

from aegra_api.core.auth_handlers import build_auth_context, handle_event
from aegra_api.models.auth import User


class TestAuthHandlersWithRealAuth:
    """Test authorization handlers with real Auth instances"""

    @pytest.fixture
    def mock_auth_file(self, tmp_path):
        """Create a temporary mock auth file with authorization handlers"""
        auth_file = tmp_path / "test_auth_with_handlers.py"
        auth_file.write_text(
            """
from langgraph_sdk import Auth

auth = Auth()

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    return {
        "identity": "test-user",
        "display_name": "Test User",
        "is_authenticated": True,
        "permissions": ["read", "write"],
    }

# Global deny handler
@auth.on
async def default_deny(ctx, value):
    return False

# Allow thread creation
@auth.on.threads.create
async def allow_thread_create(ctx, value):
    value["metadata"] = value.get("metadata", {})
    # Use getattr for User model compatibility (User model supports __getitem__ and attribute access)
    try:
        org_id = ctx.user["org_id"] if "org_id" in ctx.user else getattr(ctx.user, "org_id", "default-org")
    except (KeyError, AttributeError):
        org_id = "default-org"
    value["metadata"]["org_id"] = org_id
    return True

# Filter thread searches
@auth.on.threads.search
async def filter_threads(ctx, value):
    return {"user_id": ctx.user.identity}

# Deny assistant deletion
@auth.on.assistants.delete
async def deny_assistant_delete(ctx, value):
    return False

# Allow assistant creation with metadata injection
@auth.on.assistants.create
async def allow_assistant_create(ctx, value):
    value["metadata"] = value.get("metadata", {})
    value["metadata"]["created_by"] = ctx.user.identity
    return True
"""
        )
        return auth_file

    @pytest.fixture
    def aegra_config_with_auth_handlers(self, tmp_path, mock_auth_file, monkeypatch):
        """Create aegra.json with auth.path pointing to mock auth with handlers"""
        monkeypatch.chdir(tmp_path)

        config_file = tmp_path / "aegra.json"
        config_file.write_text(
            json.dumps(
                {
                    "graphs": {"test": "./test.py:graph"},
                    "auth": {"path": f"./{mock_auth_file.name}:auth"},
                }
            )
        )
        return config_file

    def test_load_auth_with_handlers(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that auth with handlers loads successfully"""
        from aegra_api.core.auth_middleware import LangGraphAuthBackend

        backend = LangGraphAuthBackend()
        assert backend.auth_instance is not None
        assert backend.auth_instance._handlers is not None

    @pytest.mark.asyncio
    async def test_thread_create_allowed_with_metadata_injection(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that thread creation is allowed and metadata is injected"""
        user = User(identity="test-user", org_id="org-123")
        ctx = build_auth_context(user, "threads", "create")
        value = {"metadata": {}}

        result = await handle_event(ctx, value)

        # Should allow (return None) and modify value
        assert result is None
        # Handler should inject org_id from user
        assert value["metadata"]["org_id"] == "org-123"

    @pytest.mark.asyncio
    async def test_thread_search_returns_filters(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that thread search returns filter dict"""
        user = User(identity="test-user")
        ctx = build_auth_context(user, "threads", "search")
        value = {}

        result = await handle_event(ctx, value)

        # Should return filter dict
        assert isinstance(result, dict)
        assert result["user_id"] == "test-user"

    @pytest.mark.asyncio
    async def test_assistant_delete_denied(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that assistant deletion is denied"""
        user = User(identity="test-user")
        ctx = build_auth_context(user, "assistants", "delete")
        value = {"assistant_id": "assistant-123"}

        with pytest.raises(HTTPException) as exc_info:
            await handle_event(ctx, value)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_assistant_create_allowed_with_metadata(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that assistant creation is allowed with metadata injection"""
        user = User(identity="test-user")
        ctx = build_auth_context(user, "assistants", "create")
        value = {"name": "Test Assistant", "metadata": {}}

        result = await handle_event(ctx, value)

        # Should allow and modify value
        assert result is None
        assert value["metadata"]["created_by"] == "test-user"

    @pytest.mark.asyncio
    async def test_unknown_resource_action_denied_by_default(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that unknown resource/action is denied by global handler"""
        user = User(identity="test-user")
        ctx = build_auth_context(user, "unknown", "action")
        value = {}

        with pytest.raises(HTTPException) as exc_info:
            await handle_event(ctx, value)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_handler_precedence_specific_over_general(self, aegra_config_with_auth_handlers, mock_auth_file):
        """Test that specific handler takes precedence over general"""
        user = User(identity="test-user")

        # Thread create should use specific handler (allows)
        ctx_create = build_auth_context(user, "threads", "create")
        value_create = {}
        result_create = await handle_event(ctx_create, value_create)
        assert result_create is None  # Allowed

        # Unknown action on threads should use global handler (denies)
        ctx_unknown = build_auth_context(user, "threads", "unknown_action")
        value_unknown = {}
        with pytest.raises(HTTPException) as exc_info:
            await handle_event(ctx_unknown, value_unknown)
        assert exc_info.value.status_code == 403  # Denied by global handler
