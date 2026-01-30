"""Unit tests for admin/service-level JWT authentication.

Tests admin access control that allows service accounts to bypass
user-scoping and access all resources.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt
import pytest
from langgraph_sdk import Auth

# Set up environment before importing auth module
os.environ["AUTH_TYPE"] = "custom"
os.environ["AEGRA_JWT_SECRET"] = "test-secret-for-admin-tests"
os.environ["AEGRA_JWT_ISSUERS"] = "conversation-relay,transcript-service,unknown-service"
os.environ["AEGRA_JWT_AUDIENCE"] = "test-audience"
os.environ["AEGRA_JWT_VERIFY_EXPIRATION"] = "true"
os.environ["AEGRA_JWT_LEEWAY_SECONDS"] = "30"
# Configure issuer scope mapping for tests
os.environ[
    "AEGRA_JWT_ISSUER_SCOPES"
] = "conversation-relay:admin;transcript-service:read:all"


def generate_admin_token(
    sub: str = "admin-user",
    issuer: str = None,
    scopes: list[str] = None,
    exp_seconds: int = 3600,
) -> str:
    """Generate a JWT token with admin permissions.

    Note: scopes parameter is kept for backward compatibility but is ignored.
    Actual permissions come from issuer-based mapping in auth.py.
    """
    if issuer is None:
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS")
        issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"

    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": issuer,
        "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        "scopes": scopes or [],  # Included but ignored by auth.py
    }

    return jwt.encode(payload, os.getenv("AEGRA_JWT_SECRET"), algorithm="HS256")


@pytest.fixture(autouse=True)
def clear_jwt_cache():
    """Clear JWT cache before and after each test."""
    from src.agent_server.core.jwt_utils import clear_jwt_cache as clear_cache

    clear_cache()
    yield
    clear_cache()


class TestAdminAuthentication:
    """Tests for admin JWT authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_admin_token(self):
        """Test authentication with admin scope (via issuer mapping)."""
        import auth

        # Issuer "conversation-relay" is mapped to ["admin"] scope
        token = generate_admin_token(
            sub="conversation-relay", issuer="conversation-relay"
        )

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "conversation-relay"
        assert user_dict["permissions"] == ["admin"]
        assert user_dict["is_authenticated"] is True

    @pytest.mark.asyncio
    async def test_authenticate_read_all_token(self):
        """Test authentication with read:all scope (via issuer mapping)."""
        import auth

        # Issuer "transcript-service" is mapped to ["read:all"] scope
        token = generate_admin_token(
            sub="transcript-service", issuer="transcript-service"
        )

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "transcript-service"
        assert user_dict["permissions"] == ["read:all"]

    @pytest.mark.asyncio
    async def test_authenticate_unmapped_issuer(self):
        """Test that unmapped issuers get no permissions."""
        import auth

        # Issuer "unknown-service" is not in ISSUER_SCOPE_MAP
        token = generate_admin_token(sub="unknown-user", issuer="unknown-service")

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "unknown-user"
        assert user_dict["permissions"] == []  # No permissions for unmapped issuer
        assert user_dict["is_authenticated"] is True

    @pytest.mark.asyncio
    async def test_authenticate_ignores_token_scopes(self):
        """Test that scopes in token are ignored - only issuer mapping matters."""
        import auth

        # Token claims "write:all" but issuer maps to ["admin"]
        token = generate_admin_token(
            sub="conversation-relay",
            issuer="conversation-relay",
            scopes=["write:all", "super:secret"],  # These are ignored
        )

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "conversation-relay"
        # Should get ["admin"] from issuer mapping, not token scopes
        assert user_dict["permissions"] == ["admin"]


class TestAdminAuthorization:
    """Tests for admin authorization bypass."""

    @pytest.mark.asyncio
    async def test_authorize_admin_no_filter(self):
        """Test that admin users get no owner filter."""
        import auth

        # Create mock auth context with admin permissions
        ctx = MagicMock()
        ctx.user.identity = "conversation-relay"
        ctx.user.get = lambda key, default=None: (
            ["admin"] if key == "permissions" else default
        )

        value = {}

        result = await auth.authorize(ctx, value)

        # Admin should get empty filter (no restrictions)
        assert result == {}
        # Owner metadata should still be set for new resources
        assert value["metadata"]["owner"] == "conversation-relay"

    @pytest.mark.asyncio
    async def test_authorize_read_all_no_filter(self):
        """Test that read:all users get no owner filter."""
        import auth

        ctx = MagicMock()
        ctx.user.identity = "transcript-service"
        ctx.user.get = lambda key, default=None: (
            ["read:all"] if key == "permissions" else default
        )

        value = {}

        result = await auth.authorize(ctx, value)

        # read:all should get empty filter (can read all resources)
        assert result == {}

    @pytest.mark.asyncio
    async def test_authorize_write_all_no_filter(self):
        """Test that write:all users get no owner filter."""
        import auth

        ctx = MagicMock()
        ctx.user.identity = "admin-service"
        ctx.user.get = lambda key, default=None: (
            ["write:all"] if key == "permissions" else default
        )

        value = {}

        result = await auth.authorize(ctx, value)

        # write:all should get empty filter
        assert result == {}

    @pytest.mark.asyncio
    async def test_authorize_regular_user_filtered(self):
        """Test that regular users still get owner filter."""
        import auth

        ctx = MagicMock()
        ctx.user.identity = "regular-user"
        ctx.user.get = lambda key, default=None: default  # No permissions

        value = {}

        result = await auth.authorize(ctx, value)

        # Regular user should be filtered by owner
        assert result == {"owner": "regular-user"}
        assert value["metadata"]["owner"] == "regular-user"

    @pytest.mark.asyncio
    async def test_authorize_admin_preserves_existing_owner(self):
        """Test that admin doesn't overwrite existing owner metadata."""
        import auth

        ctx = MagicMock()
        ctx.user.identity = "admin"
        ctx.user.get = lambda key, default=None: (
            ["admin"] if key == "permissions" else default
        )

        value = {"metadata": {"owner": "original-owner"}}

        result = await auth.authorize(ctx, value)

        # Admin gets no filter
        assert result == {}
        # Existing owner should be preserved
        assert value["metadata"]["owner"] == "original-owner"
