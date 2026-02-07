"""Unit tests for auth context utilities"""

import pytest
from starlette.authentication import AuthCredentials, SimpleUser

from aegra_api.core.auth_ctx import get_auth_ctx, with_auth_ctx


class TestGetAuthCtx:
    """Test get_auth_ctx function"""

    @pytest.mark.asyncio
    async def test_get_auth_ctx_returns_none_by_default(self):
        """Test that get_auth_ctx returns None when not set"""
        ctx = get_auth_ctx()
        assert ctx is None


class TestWithAuthCtx:
    """Test with_auth_ctx context manager"""

    @pytest.mark.asyncio
    async def test_with_auth_ctx_sets_user(self):
        """Test setting auth context with user"""
        user = SimpleUser("test_user")

        async with with_auth_ctx(user):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.user == user

        # Context should be cleared after exiting
        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_sets_permissions_as_list(self):
        """Test setting auth context with permissions as list"""
        user = SimpleUser("test_user")
        permissions = ["read", "write"]

        async with with_auth_ctx(user, permissions):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.permissions == permissions

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_sets_permissions_as_auth_credentials(self):
        """Test setting auth context with AuthCredentials"""
        user = SimpleUser("test_user")
        credentials = AuthCredentials(["admin", "user"])

        async with with_auth_ctx(user, credentials):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert "admin" in ctx.permissions
            assert "user" in ctx.permissions

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_none_user_none_permissions(self):
        """Test with None user and None permissions"""
        async with with_auth_ctx(None, None):
            ctx = get_auth_ctx()
            assert ctx is None

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_none_user_with_permissions(self):
        """Test with None user but with permissions"""
        permissions = ["read"]

        async with with_auth_ctx(None, permissions):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.user is None
            assert ctx.permissions == permissions

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_user_without_permissions(self):
        """Test with user but no permissions"""
        user = SimpleUser("test_user")

        async with with_auth_ctx(user, None):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.user == user
            assert ctx.permissions == []

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_nested(self):
        """Test nested auth contexts"""
        user1 = SimpleUser("user1")
        user2 = SimpleUser("user2")

        async with with_auth_ctx(user1, ["read"]):
            ctx1 = get_auth_ctx()
            assert ctx1.user == user1
            assert ctx1.permissions == ["read"]

            async with with_auth_ctx(user2, ["write"]):
                ctx2 = get_auth_ctx()
                assert ctx2.user == user2
                assert ctx2.permissions == ["write"]

            # After inner context exits, outer context should be restored
            ctx1_restored = get_auth_ctx()
            assert ctx1_restored.user == user1
            assert ctx1_restored.permissions == ["read"]

        # After all contexts exit, should be None
        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_exception_cleanup(self):
        """Test that context is cleaned up even on exception"""
        user = SimpleUser("test_user")

        with pytest.raises(ValueError):
            async with with_auth_ctx(user, ["read"]):
                ctx = get_auth_ctx()
                assert ctx is not None
                raise ValueError("Test exception")

        # Context should still be cleared
        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_empty_permissions_list(self):
        """Test with empty permissions list"""
        user = SimpleUser("test_user")

        async with with_auth_ctx(user, []):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.user == user
            assert ctx.permissions == []

        ctx = get_auth_ctx()
        assert ctx is None

    @pytest.mark.asyncio
    async def test_with_auth_ctx_multiple_permissions(self):
        """Test with multiple permissions"""
        user = SimpleUser("test_user")
        permissions = ["read", "write", "delete", "admin"]

        async with with_auth_ctx(user, permissions):
            ctx = get_auth_ctx()
            assert ctx is not None
            assert ctx.permissions == permissions

        ctx = get_auth_ctx()
        assert ctx is None
