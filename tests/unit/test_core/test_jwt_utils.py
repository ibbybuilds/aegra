"""Unit tests for JWT authentication utilities.

Tests JWT verification, caching behavior, and error handling.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.agent_server.core.jwt_utils import (
    JWTAuthenticationError,
    JWTConfigurationError,
    clear_jwt_cache,
    get_jwt_cache_info,
    validate_jwt_configuration,
    verify_jwt_token,
)


@pytest.fixture(autouse=True)
def setup_jwt_config(monkeypatch):
    """Set up JWT configuration for tests."""
    monkeypatch.setenv("AEGRA_JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("AEGRA_JWT_SECRET", "test-secret-key-for-unit-tests")
    monkeypatch.setenv("AEGRA_JWT_ISSUERS", "test-issuer,other-issuer")  # Multiple issuers
    monkeypatch.setenv("AEGRA_JWT_AUDIENCE", "test-audience")
    monkeypatch.setenv("AEGRA_JWT_VERIFY_EXPIRATION", "true")
    monkeypatch.setenv("AEGRA_JWT_LEEWAY_SECONDS", "30")

    # Clear cache before each test
    clear_jwt_cache()

    yield

    # Clear cache after each test
    clear_jwt_cache()


@pytest.fixture
def jwt_secret():
    """Get JWT secret from environment."""
    return os.getenv("AEGRA_JWT_SECRET")


@pytest.fixture
def jwt_issuers():
    """Get JWT issuers from environment."""
    issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
    return [iss.strip() for iss in issuers_str.split(",")] if issuers_str else []


@pytest.fixture
def jwt_audience():
    """Get JWT audience from environment."""
    return os.getenv("AEGRA_JWT_AUDIENCE")


def generate_test_token(
    sub: str = "test-user",
    exp_seconds: int = 3600,
    secret: str = None,
    issuer: str = None,
    audience: str = None,
    **extra_claims,
) -> str:
    """Generate a test JWT token."""
    secret = secret or os.getenv("AEGRA_JWT_SECRET")
    # Use first issuer from list if not specified
    if not issuer:
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
        issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"
    audience = audience or os.getenv("AEGRA_JWT_AUDIENCE")
    
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_seconds)).timestamp()),
        **extra_claims,
    }
    
    return jwt.encode(payload, secret, algorithm="HS256")


class TestJWTConfiguration:
    """Tests for JWT configuration validation."""

    def test_validate_configuration_success(self):
        """Test successful configuration validation."""
        # Should not raise any exception
        validate_jwt_configuration()

    def test_validate_configuration_missing_secret(self, monkeypatch):
        """Test configuration validation with missing secret."""
        monkeypatch.delenv("AEGRA_JWT_SECRET")

        with pytest.raises(JWTConfigurationError) as exc_info:
            validate_jwt_configuration()

        assert "AEGRA_JWT_SECRET" in str(exc_info.value)

    def test_validate_configuration_missing_issuer(self, monkeypatch):
        """Test configuration validation with missing issuer."""
        monkeypatch.delenv("AEGRA_JWT_ISSUERS")

        with pytest.raises(JWTConfigurationError) as exc_info:
            validate_jwt_configuration()

        assert "AEGRA_JWT_ISSUERS" in str(exc_info.value)

    def test_validate_configuration_missing_audience(self, monkeypatch):
        """Test configuration validation with missing audience."""
        monkeypatch.delenv("AEGRA_JWT_AUDIENCE")

        with pytest.raises(JWTConfigurationError) as exc_info:
            validate_jwt_configuration()

        assert "AEGRA_JWT_AUDIENCE" in str(exc_info.value)


class TestJWTVerification:
    """Tests for JWT token verification."""

    def test_verify_valid_token(self):
        """Test verification of a valid token."""
        token = generate_test_token(sub="user-123")

        payload = verify_jwt_token(token)

        assert payload["sub"] == "user-123"
        # Verify issuer is one of the trusted issuers
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
        trusted_issuers = [iss.strip() for iss in issuers_str.split(",")]
        assert payload["iss"] in trusted_issuers
        assert payload["aud"] == os.getenv("AEGRA_JWT_AUDIENCE")
        assert "iat" in payload
        assert "exp" in payload

    def test_verify_token_with_optional_claims(self):
        """Test verification of token with optional claims."""
        token = generate_test_token(
            sub="user-123",
            name="Test User",
            email="test@example.com",
            org="test-org",
            scopes=["read", "write"],
        )
        
        payload = verify_jwt_token(token)
        
        assert payload["sub"] == "user-123"
        assert payload["name"] == "Test User"
        assert payload["email"] == "test@example.com"
        assert payload["org"] == "test-org"
        assert payload["scopes"] == ["read", "write"]

    def test_verify_expired_token(self):
        """Test verification of an expired token."""
        # Generate token that expired 1 hour ago
        token = generate_test_token(exp_seconds=-3600)
        
        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token(token)
        
        assert "expired" in str(exc_info.value).lower()

    def test_verify_token_invalid_signature(self):
        """Test verification with invalid signature."""
        token = generate_test_token(secret="wrong-secret")
        
        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token(token)
        
        assert "signature" in str(exc_info.value).lower()

    def test_verify_token_invalid_issuer(self):
        """Test verification with invalid issuer."""
        token = generate_test_token(issuer="wrong-issuer")

        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token(token)

        assert "issuer" in str(exc_info.value).lower()

    def test_verify_token_with_alternate_issuer(self):
        """Test verification with second trusted issuer."""
        # Use the second issuer from the list (other-issuer)
        token = generate_test_token(issuer="other-issuer", sub="user-456")

        payload = verify_jwt_token(token)

        assert payload["sub"] == "user-456"
        assert payload["iss"] == "other-issuer"

    def test_verify_token_invalid_audience(self):
        """Test verification with invalid audience."""
        token = generate_test_token(audience="wrong-audience")
        
        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token(token)
        
        assert "audience" in str(exc_info.value).lower()

    def test_verify_token_missing_sub_claim(self):
        """Test verification of token missing 'sub' claim."""
        secret = os.getenv("AEGRA_JWT_SECRET")
        issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
        issuer = issuers_str.split(",")[0].strip() if issuers_str else "test-issuer"
        audience = os.getenv("AEGRA_JWT_AUDIENCE")

        now = datetime.now(timezone.utc)
        payload = {
            # Missing 'sub' claim
            "iss": issuer,
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=3600)).timestamp()),
        }

        token = jwt.encode(payload, secret, algorithm="HS256")
        
        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token(token)
        
        assert "sub" in str(exc_info.value).lower()

    def test_verify_malformed_token(self):
        """Test verification of a malformed token."""
        with pytest.raises(JWTAuthenticationError) as exc_info:
            verify_jwt_token("not.a.valid.jwt.token")
        
        assert "decode" in str(exc_info.value).lower()


class TestJWTCaching:
    """Tests for JWT verification caching."""

    def test_cache_hit_same_token(self):
        """Test that cache is used for the same token."""
        token = generate_test_token()
        
        # First call (cache miss)
        payload1 = verify_jwt_token(token)
        cache_info1 = get_jwt_cache_info()
        
        # Second call (cache hit)
        payload2 = verify_jwt_token(token)
        cache_info2 = get_jwt_cache_info()
        
        assert payload1 == payload2
        assert cache_info2["hits"] == cache_info1["hits"] + 1
        assert cache_info2["misses"] == cache_info1["misses"]

    def test_cache_miss_different_tokens(self):
        """Test that different tokens result in cache misses."""
        token1 = generate_test_token(sub="user-1")
        token2 = generate_test_token(sub="user-2")
        
        verify_jwt_token(token1)
        cache_info1 = get_jwt_cache_info()
        
        verify_jwt_token(token2)
        cache_info2 = get_jwt_cache_info()
        
        # Both should be cache misses
        assert cache_info2["misses"] == cache_info1["misses"] + 1

    def test_clear_cache(self):
        """Test cache clearing."""
        token = generate_test_token()
        
        # Verify token to populate cache
        verify_jwt_token(token)
        cache_info1 = get_jwt_cache_info()
        assert cache_info1["currsize"] > 0
        
        # Clear cache
        clear_jwt_cache()
        cache_info2 = get_jwt_cache_info()
        
        assert cache_info2["currsize"] == 0
        assert cache_info2["hits"] == 0
        assert cache_info2["misses"] == 0

    def test_cache_performance(self):
        """Test that cached verification is faster than uncached."""
        token = generate_test_token()
        
        # First call (uncached) - measure time
        start_uncached = time.perf_counter()
        verify_jwt_token(token)
        time_uncached = time.perf_counter() - start_uncached
        
        # Second call (cached) - measure time
        start_cached = time.perf_counter()
        verify_jwt_token(token)
        time_cached = time.perf_counter() - start_cached
        
        # Cached should be significantly faster
        # We expect >10x improvement, but use >2x for test stability
        assert time_cached < time_uncached / 2, (
            f"Cached verification not faster enough: "
            f"uncached={time_uncached*1000:.2f}ms, cached={time_cached*1000:.2f}ms"
        )
        
        # Verify performance targets from plan
        assert time_cached < 0.001, (  # <1ms for cached
            f"Cached verification too slow: {time_cached*1000:.2f}ms"
        )
        assert time_uncached < 0.005, (  # <5ms for uncached
            f"Uncached verification too slow: {time_uncached*1000:.2f}ms"
        )


class TestJWTCacheInfo:
    """Tests for cache info retrieval."""

    def test_get_cache_info_initial(self):
        """Test cache info when cache is empty."""
        info = get_jwt_cache_info()
        
        assert info["hits"] == 0
        assert info["misses"] == 0
        assert info["currsize"] == 0
        assert info["maxsize"] == 1000  # As defined in jwt_utils.py

    def test_get_cache_info_after_operations(self):
        """Test cache info after some operations."""
        token1 = generate_test_token(sub="user-1")
        token2 = generate_test_token(sub="user-2")
        
        # First verifications (2 misses)
        verify_jwt_token(token1)
        verify_jwt_token(token2)
        
        # Second verifications (2 hits)
        verify_jwt_token(token1)
        verify_jwt_token(token2)
        
        info = get_jwt_cache_info()
        
        assert info["hits"] == 2
        assert info["misses"] == 2
        assert info["currsize"] == 2
