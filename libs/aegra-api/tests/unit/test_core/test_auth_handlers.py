"""Unit tests for authorization handlers"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from langgraph_sdk import Auth
from langgraph_sdk.auth.types import AuthContext as LangGraphAuthContext

from aegra_api.core.auth_handlers import (
    AuthContextWrapper,
    build_auth_context,
    handle_event,
)
from aegra_api.models.auth import User


class TestAuthContextWrapper:
    """Test AuthContextWrapper class"""

    def test_initialization(self):
        """Test AuthContextWrapper initialization"""
        user = User(identity="user-123", permissions=["read", "write"])
        ctx = AuthContextWrapper(user, "threads", "create")

        assert ctx.user == user
        assert ctx.resource == "threads"
        assert ctx.action == "create"
        assert ctx.permissions == ["read", "write"]

    def test_to_langgraph_context(self):
        """Test conversion to LangGraph AuthContext"""
        user = User(
            identity="user-123",
            permissions=["read", "write"],
            display_name="Test User",
        )
        ctx = AuthContextWrapper(user, "threads", "create")
        langgraph_ctx = ctx.to_langgraph_context()

        assert isinstance(langgraph_ctx, LangGraphAuthContext)
        assert langgraph_ctx.resource == "threads"
        assert langgraph_ctx.action == "create"
        assert langgraph_ctx.permissions == ["read", "write"]
        assert langgraph_ctx.user.identity == "user-123"
        assert langgraph_ctx.user.display_name == "Test User"


class TestBuildAuthContext:
    """Test build_auth_context helper"""

    def test_build_auth_context(self):
        """Test building auth context"""
        user = User(identity="user-123", permissions=["read"])
        ctx = build_auth_context(user, "assistants", "create")

        assert isinstance(ctx, AuthContextWrapper)
        assert ctx.user == user
        assert ctx.resource == "assistants"
        assert ctx.action == "create"


class TestHandleEvent:
    """Test handle_event function"""

    @pytest.mark.asyncio
    async def test_no_context_returns_none(self):
        """Test that None context returns None (allows request)"""
        result = await handle_event(None, {})

        assert result is None

    @pytest.mark.asyncio
    async def test_no_auth_instance_returns_none(self):
        """Test that no auth instance returns None (allows request)"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        with patch("aegra_api.core.auth_handlers.get_auth_instance", return_value=None):
            result = await handle_event(ctx, {})

            assert result is None

    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self):
        """Test that no handler for resource/action returns None"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            assert result is None

    @pytest.mark.asyncio
    async def test_handler_returns_true_allows(self):
        """Test that handler returning True allows request"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(return_value=True)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            assert result is None
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_returns_none_allows(self):
        """Test that handler returning None allows request"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(return_value=None)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            assert result is None

    @pytest.mark.asyncio
    async def test_handler_returns_false_denies(self):
        """Test that handler returning False denies request"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(return_value=False)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await handle_event(ctx, {})

            assert exc_info.value.status_code == 403
            assert "Forbidden" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handler_returns_filter_dict(self):
        """Test that handler returning filter dict returns filters"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "search")

        filter_dict = {"user_id": "user-123"}
        mock_handler = AsyncMock(return_value=filter_dict)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "search"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            assert result == filter_dict

    @pytest.mark.asyncio
    async def test_handler_modifies_value(self):
        """Test that handler can modify the value dict"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        def handler_side_effect(ctx, value):
            value["metadata"] = {"org_id": "org-456"}
            return True

        mock_handler = AsyncMock(side_effect=handler_side_effect)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        value = {}
        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            await handle_event(ctx, value)

            assert value["metadata"] == {"org_id": "org-456"}

    @pytest.mark.asyncio
    async def test_handler_raises_http_exception(self):
        """Test that handler raising HTTPException is converted"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        # Create a proper HTTPException-like exception
        class MockHTTPException(Exception):
            def __init__(self, status_code, detail, headers=None):
                self.status_code = status_code
                self.detail = detail
                self.headers = headers
                super().__init__(detail)

        mock_exception = MockHTTPException(403, "Access denied")

        mock_handler = AsyncMock(side_effect=mock_exception)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        # Mock Auth.exceptions.HTTPException to match our exception type
        mock_auth.exceptions = Mock()
        mock_auth.exceptions.HTTPException = MockHTTPException

        with (
            patch(
                "aegra_api.core.auth_handlers.get_auth_instance",
                return_value=mock_auth,
            ),
            patch("aegra_api.core.auth_handlers.Auth") as mock_auth_class,
        ):
            mock_auth_class.exceptions.HTTPException = MockHTTPException
            with pytest.raises(HTTPException) as exc_info:
                await handle_event(ctx, {})

            assert exc_info.value.status_code == 403
            assert "Access denied" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handler_raises_assertion_error(self):
        """Test that handler raising AssertionError is converted to 403"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(side_effect=AssertionError("Not authorized"))
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await handle_event(ctx, {})

            assert exc_info.value.status_code == 403
            assert "Not authorized" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handler_raises_unexpected_exception(self):
        """Test that handler raising unexpected exception returns 500"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(side_effect=ValueError("Unexpected error"))
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await handle_event(ctx, {})

            assert exc_info.value.status_code == 500
            assert "Authorization error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handler_returns_invalid_type(self):
        """Test that handler returning invalid type raises 500"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(return_value="invalid")
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await handle_event(ctx, {})

            assert exc_info.value.status_code == 500
            assert "invalid type" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_handler_resolution_priority(self):
        """Test handler resolution priority (most specific first)"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        # Create handlers at different specificity levels
        specific_handler = AsyncMock(return_value={"specific": True})
        resource_handler = AsyncMock(return_value={"resource": True})
        global_handler = AsyncMock(return_value={"global": True})

        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {
            ("threads", "create"): [specific_handler],  # Most specific
            ("threads", "*"): [resource_handler],  # Resource-specific
            ("*", "*"): [global_handler],  # Global
        }
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            # Should use most specific handler
            assert result == {"specific": True}
            specific_handler.assert_called_once()
            resource_handler.assert_not_called()
            global_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_resolution_fallback_to_resource(self):
        """Test handler resolution falls back to resource-specific handler"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "update")

        resource_handler = AsyncMock(return_value={"resource": True})
        global_handler = AsyncMock(return_value={"global": True})

        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {
            ("threads", "*"): [resource_handler],  # Resource-specific
            ("*", "*"): [global_handler],  # Global
        }
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            # Should use resource-specific handler
            assert result == {"resource": True}
            resource_handler.assert_called_once()
            global_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_resolution_fallback_to_global(self):
        """Test handler resolution falls back to global handler"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "unknown", "action")

        global_handler = AsyncMock(return_value={"global": True})

        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {
            ("*", "*"): [global_handler],  # Global
        }
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            result = await handle_event(ctx, {})

            # Should use global handler
            assert result == {"global": True}
            global_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_cache_usage(self):
        """Test that handler cache is used and populated"""
        user = User(identity="user-123")
        ctx = build_auth_context(user, "threads", "create")

        mock_handler = AsyncMock(return_value=True)
        mock_auth = Mock(spec=Auth)
        mock_auth._handlers = {("threads", "create"): [mock_handler]}
        mock_auth._global_handlers = []
        mock_auth._handler_cache = {}

        with patch(
            "aegra_api.core.auth_handlers.get_auth_instance",
            return_value=mock_auth,
        ):
            # First call
            await handle_event(ctx, {})
            assert ("threads", "create") in mock_auth._handler_cache

            # Second call should use cache
            await handle_event(ctx, {})
            # Handler should still be called (cache stores handler, not result)
            assert mock_handler.call_count == 2
