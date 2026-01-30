"""Unit tests for JWT authentication integration.

Tests the JWT authentication flow in auth.py, including token extraction,
claims mapping, and error handling.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from langgraph_sdk import Auth


def generate_test_token(
    sub: str = "test-user",
    exp_seconds: int = 3600,
    **extra_claims,
) -> str:
    """Generate a test JWT token."""
    # Use first issuer from the list
    issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
    issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"

    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": issuer,
        "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        **extra_claims,
    }

    return jwt.encode(payload, os.getenv("AEGRA_JWT_SECRET"), algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_jwt_test_env(monkeypatch):
    """Set up environment for JWT authentication tests."""
    # Configure environment for JWT tests
    monkeypatch.setenv("AUTH_TYPE", "custom")
    monkeypatch.setenv("AEGRA_JWT_SECRET", "test-secret-for-auth-tests")
    monkeypatch.setenv("AEGRA_JWT_ISSUERS", "test-issuer,other-issuer")
    monkeypatch.setenv("AEGRA_JWT_AUDIENCE", "test-audience")
    monkeypatch.setenv("AEGRA_JWT_VERIFY_EXPIRATION", "true")
    monkeypatch.setenv("AEGRA_JWT_LEEWAY_SECONDS", "30")
    monkeypatch.setenv("AEGRA_JWT_ISSUER_SCOPES", "")  # Empty mapping

    # Clear JWT cache after environment setup
    from src.agent_server.core.jwt_utils import clear_jwt_cache as clear_cache

    clear_cache()
    yield
    clear_cache()


class TestJWTAuthenticationFlow:
    """Tests for JWT authentication flow in auth.py."""

    @pytest.mark.asyncio
    async def test_authenticate_valid_token(self):
        """Test authentication with a valid JWT token."""
        # Import auth module (must be after env vars are set)
        import auth

        token = generate_test_token(
            sub="user-123",
            name="John Doe",
            email="john@example.com",
            org="acme-corp",
            scopes=["read", "write"],  # Included but ignored
        )

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "user-123"
        assert user_dict["display_name"] == "John Doe"
        assert user_dict["email"] == "john@example.com"
        assert user_dict["org_id"] == "acme-corp"
        # Issuer "test-issuer" is not mapped, so no permissions granted
        assert user_dict["permissions"] == []
        assert user_dict["is_authenticated"] is True

    @pytest.mark.asyncio
    async def test_authenticate_minimal_token(self):
        """Test authentication with minimal JWT token (only required claims)."""
        import auth

        token = generate_test_token(sub="user-123")

        headers = {"Authorization": f"Bearer {token}"}

        user_dict = await auth.authenticate(headers)

        assert user_dict["identity"] == "user-123"
        assert user_dict["is_authenticated"] is True
        # Optional fields should not be present if not in token
        assert "display_name" not in user_dict
        assert "email" not in user_dict
        assert "org_id" not in user_dict
        # Permissions always present (from issuer mapping), but empty for unmapped issuer
        assert user_dict["permissions"] == []

    @pytest.mark.asyncio
    async def test_authenticate_lowercase_header(self):
        """Test authentication with lowercase authorization header."""
        import auth
        
        token = generate_test_token(sub="user-123")
        
        headers = {"authorization": f"Bearer {token}"}
        
        user_dict = await auth.authenticate(headers)
        
        assert user_dict["identity"] == "user-123"

    @pytest.mark.asyncio
    async def test_authenticate_bytes_header(self):
        """Test authentication with bytes authorization header."""
        import auth
        
        token = generate_test_token(sub="user-123")
        
        headers = {b"Authorization": f"Bearer {token}".encode()}
        
        user_dict = await auth.authenticate(headers)
        
        assert user_dict["identity"] == "user-123"

    @pytest.mark.asyncio
    async def test_authenticate_missing_header(self):
        """Test authentication with missing Authorization header."""
        import auth
        
        headers = {}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_format(self):
        """Test authentication with invalid authorization format."""
        import auth
        
        headers = {"Authorization": "InvalidFormat token"}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401
        assert "bearer" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_empty_token(self):
        """Test authentication with empty token after Bearer prefix."""
        import auth
        
        headers = {"Authorization": "Bearer   "}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401
        assert "empty" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_expired_token(self):
        """Test authentication with expired token."""
        import auth
        
        # Generate token that expired 1 hour ago
        token = generate_test_token(sub="user-123", exp_seconds=-3600)
        
        headers = {"Authorization": f"Bearer {token}"}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_signature(self):
        """Test authentication with invalid signature."""
        import auth

        # Generate token with wrong secret
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
        issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-123",
            "iss": issuer,
            "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=3600)).timestamp()),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401
        assert "signature" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_missing_sub_claim(self):
        """Test authentication with token missing 'sub' claim."""
        import auth

        # Generate token without sub claim
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
        issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"

        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer,
            "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=3600)).timestamp()),
        }
        token = jwt.encode(payload, os.getenv("AEGRA_JWT_SECRET"), algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authenticate(headers)
        
        assert exc_info.value.status_code == 401


class TestJWTAuthorization:
    """Tests for authorization with JWT authentication."""

    @pytest.mark.asyncio
    async def test_authorize_user_scoped_access(self):
        """Test that authorization returns user-scoped filter."""
        import auth
        
        # Create mock auth context
        ctx = MagicMock()
        ctx.user.identity = "user-123"
        
        value = {}
        
        result = await auth.authorize(ctx, value)
        
        assert result == {"owner": "user-123"}
        assert value["metadata"]["owner"] == "user-123"

    @pytest.mark.asyncio
    async def test_authorize_missing_identity(self):
        """Test authorization with missing user identity."""
        import auth
        
        # Create mock auth context with no identity
        ctx = MagicMock()
        ctx.user.identity = None
        
        value = {}
        
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await auth.authorize(ctx, value)
        
        assert exc_info.value.status_code == 401


class TestJWTCachingIntegration:
    """Tests for JWT caching in authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_uses_cache(self):
        """Test that repeated authentication uses cache."""
        import auth
        from src.agent_server.core.jwt_utils import get_jwt_cache_info
        
        token = generate_test_token(sub="user-123")
        headers = {"Authorization": f"Bearer {token}"}
        
        # First authentication (cache miss)
        await auth.authenticate(headers)
        cache_info1 = get_jwt_cache_info()
        
        # Second authentication (cache hit)
        await auth.authenticate(headers)
        cache_info2 = get_jwt_cache_info()
        
        # Verify cache was used
        assert cache_info2["hits"] == cache_info1["hits"] + 1
        assert cache_info2["misses"] == cache_info1["misses"]
