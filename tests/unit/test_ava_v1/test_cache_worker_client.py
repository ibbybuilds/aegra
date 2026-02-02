"""Tests for cache-worker client JWT authentication."""

import os
import time
from unittest.mock import patch

import jwt
import pytest

from graphs.ava_v1.shared_libraries.cache_worker_client import (
    CacheWorkerConfigError,
    _generate_cache_worker_jwt,
    _get_cache_worker_config,
    _is_jwt_enabled,
    get_cache_worker_client,
)


class TestJWTEnabled:
    """Tests for JWT enable/disable logic."""

    def test_explicit_true(self, monkeypatch):
        """JWT enabled when explicitly set to true."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("ENV_MODE", "LOCAL")
        assert _is_jwt_enabled() is True

    def test_explicit_false(self, monkeypatch):
        """JWT disabled when explicitly set to false."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        monkeypatch.setenv("ENV_MODE", "PRODUCTION")
        assert _is_jwt_enabled() is False

    def test_production_auto_enabled(self, monkeypatch):
        """JWT auto-enabled in production environment."""
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)
        monkeypatch.setenv("ENV_MODE", "PRODUCTION")
        assert _is_jwt_enabled() is True

    def test_development_auto_enabled(self, monkeypatch):
        """JWT auto-enabled in development environment (staging)."""
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)
        monkeypatch.setenv("ENV_MODE", "DEVELOPMENT")
        assert _is_jwt_enabled() is True

    def test_local_auto_disabled(self, monkeypatch):
        """JWT auto-disabled in local environment."""
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)
        monkeypatch.setenv("ENV_MODE", "LOCAL")
        assert _is_jwt_enabled() is False

    def test_default_local(self, monkeypatch):
        """Default is local environment (JWT disabled)."""
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)
        monkeypatch.delenv("ENV_MODE", raising=False)
        assert _is_jwt_enabled() is False


class TestCacheWorkerConfig:
    """Tests for cache-worker configuration loading."""

    def test_default_config_jwt_disabled(self, monkeypatch):
        """Default configuration with JWT disabled."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        config = _get_cache_worker_config()

        assert config["url"] == "http://localhost:8080"
        assert config["jwt_enabled"] is False
        assert config["jwt_secret"] is None
        assert config["jwt_issuer"] == "aegra"
        assert config["jwt_audience"] == "cache-worker"
        assert config["jwt_expiry_seconds"] == 3600

    def test_custom_config_jwt_enabled(self, monkeypatch):
        """Custom configuration with JWT enabled."""
        monkeypatch.setenv("CACHE_WORKER_URL", "https://cache-worker.example.com")
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret-256-bit")
        monkeypatch.setenv("CACHE_WORKER_JWT_ISSUER", "custom-issuer")
        monkeypatch.setenv("CACHE_WORKER_JWT_AUDIENCE", "custom-audience")
        monkeypatch.setenv("CACHE_WORKER_JWT_EXPIRY_SECONDS", "7200")

        config = _get_cache_worker_config()

        assert config["url"] == "https://cache-worker.example.com"
        assert config["jwt_enabled"] is True
        assert config["jwt_secret"] == "test-secret-256-bit"
        assert config["jwt_issuer"] == "custom-issuer"
        assert config["jwt_audience"] == "custom-audience"
        assert config["jwt_expiry_seconds"] == 7200

    def test_error_when_jwt_enabled_without_secret(self, monkeypatch):
        """Error raised when JWT enabled but secret missing."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)

        with pytest.raises(CacheWorkerConfigError) as exc_info:
            _get_cache_worker_config()

        assert "CACHE_WORKER_JWT_SECRET is required" in str(exc_info.value)

    def test_no_error_when_jwt_disabled_without_secret(self, monkeypatch):
        """No error when JWT disabled and secret missing."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)

        config = _get_cache_worker_config()
        assert config["jwt_enabled"] is False
        assert config["jwt_secret"] is None


class TestJWTGeneration:
    """Tests for JWT token generation."""

    def test_jwt_structure(self, monkeypatch):
        """Generated JWT has correct structure and claims."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")
        monkeypatch.setenv("CACHE_WORKER_JWT_ISSUER", "aegra")
        monkeypatch.setenv("CACHE_WORKER_JWT_AUDIENCE", "cache-worker")
        monkeypatch.setenv("CACHE_WORKER_JWT_EXPIRY_SECONDS", "3600")

        token = _generate_cache_worker_jwt()

        # Decode without verification to check structure
        decoded = jwt.decode(
            token, options={"verify_signature": False, "verify_exp": False}
        )

        assert decoded["iss"] == "aegra"
        assert decoded["aud"] == "cache-worker"
        assert decoded["sub"] == "aegra-service"
        assert "iat" in decoded
        assert "exp" in decoded

    def test_jwt_algorithm(self, monkeypatch):
        """JWT uses HS256 algorithm."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")

        token = _generate_cache_worker_jwt()

        # Verify with correct secret and algorithm
        decoded = jwt.decode(
            token,
            "test-secret",
            algorithms=["HS256"],
            audience="cache-worker",
            options={"verify_exp": False},
        )
        assert decoded["iss"] == "aegra"

    def test_jwt_expiration(self, monkeypatch):
        """JWT expires after configured duration."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")
        monkeypatch.setenv("CACHE_WORKER_JWT_EXPIRY_SECONDS", "3600")

        with patch("time.time", return_value=1000000):
            token = _generate_cache_worker_jwt()

        decoded = jwt.decode(
            token,
            "test-secret",
            algorithms=["HS256"],
            audience="cache-worker",
            options={"verify_exp": False},
        )

        assert decoded["iat"] == 1000000
        assert decoded["exp"] == 1003600  # 1000000 + 3600

    def test_jwt_custom_claims(self, monkeypatch):
        """JWT includes custom issuer and audience."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")
        monkeypatch.setenv("CACHE_WORKER_JWT_ISSUER", "custom-issuer")
        monkeypatch.setenv("CACHE_WORKER_JWT_AUDIENCE", "custom-audience")

        token = _generate_cache_worker_jwt()

        decoded = jwt.decode(
            token,
            "test-secret",
            algorithms=["HS256"],
            audience="custom-audience",
            options={"verify_exp": False},
        )

        assert decoded["iss"] == "custom-issuer"
        assert decoded["aud"] == "custom-audience"


class TestClientFactory:
    """Tests for httpx.AsyncClient factory."""

    def test_client_without_jwt(self, monkeypatch):
        """Client created without Authorization header when JWT disabled."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        monkeypatch.setenv("CACHE_WORKER_URL", "http://localhost:8080")

        client = get_cache_worker_client()

        assert client.base_url == "http://localhost:8080"
        assert "Authorization" not in client.headers
        assert client.timeout.read == 30.0

    def test_client_with_jwt(self, monkeypatch):
        """Client created with Authorization header when JWT enabled."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")
        monkeypatch.setenv("CACHE_WORKER_URL", "https://cache-worker.example.com")

        client = get_cache_worker_client()

        assert client.base_url == "https://cache-worker.example.com"
        assert "Authorization" in client.headers
        assert client.headers["Authorization"].startswith("Bearer ")
        assert client.timeout.read == 30.0

    def test_client_jwt_token_valid(self, monkeypatch):
        """Authorization header contains valid JWT."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "true")
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "test-secret")

        client = get_cache_worker_client()

        token = client.headers["Authorization"].replace("Bearer ", "")
        decoded = jwt.decode(
            token,
            "test-secret",
            algorithms=["HS256"],
            audience="cache-worker",
            options={"verify_exp": False},
        )

        assert decoded["iss"] == "aegra"
        assert decoded["aud"] == "cache-worker"

    def test_client_custom_base_url(self, monkeypatch):
        """Client uses custom base URL."""
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        monkeypatch.setenv(
            "CACHE_WORKER_URL", "https://cache-worker-staging.railway.app"
        )

        client = get_cache_worker_client()

        assert client.base_url == "https://cache-worker-staging.railway.app"


class TestErrorHandling:
    """Tests for error handling."""

    def test_missing_secret_production_mode(self, monkeypatch):
        """Error when running in production without JWT secret."""
        monkeypatch.setenv("ENV_MODE", "PRODUCTION")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)

        with pytest.raises(CacheWorkerConfigError) as exc_info:
            get_cache_worker_client()

        assert "CACHE_WORKER_JWT_SECRET is required" in str(exc_info.value)

    def test_missing_secret_development_mode(self, monkeypatch):
        """Error when running in development/staging without JWT secret."""
        monkeypatch.setenv("ENV_MODE", "DEVELOPMENT")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)

        with pytest.raises(CacheWorkerConfigError) as exc_info:
            get_cache_worker_client()

        assert "CACHE_WORKER_JWT_SECRET is required" in str(exc_info.value)

    def test_explicit_disable_overrides_production(self, monkeypatch):
        """Explicit disable overrides production auto-enable."""
        monkeypatch.setenv("ENV_MODE", "PRODUCTION")
        monkeypatch.setenv("CACHE_WORKER_JWT_ENABLED", "false")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)

        # Should not raise error
        client = get_cache_worker_client()
        assert "Authorization" not in client.headers


class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_local_development_scenario(self, monkeypatch):
        """Local development: JWT disabled, no secret required."""
        monkeypatch.setenv("ENV_MODE", "LOCAL")
        monkeypatch.setenv("CACHE_WORKER_URL", "http://localhost:8080")
        monkeypatch.delenv("CACHE_WORKER_JWT_SECRET", raising=False)
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)

        client = get_cache_worker_client()

        assert client.base_url == "http://localhost:8080"
        assert "Authorization" not in client.headers

    def test_staging_scenario(self, monkeypatch):
        """Staging: JWT auto-enabled with secret."""
        monkeypatch.setenv("ENV_MODE", "DEVELOPMENT")
        monkeypatch.setenv(
            "CACHE_WORKER_URL", "https://cache-worker-staging.railway.app"
        )
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "staging-secret-256-bit")
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)

        client = get_cache_worker_client()

        assert client.base_url == "https://cache-worker-staging.railway.app"
        assert "Authorization" in client.headers

    def test_production_scenario(self, monkeypatch):
        """Production: JWT auto-enabled with secret."""
        monkeypatch.setenv("ENV_MODE", "PRODUCTION")
        monkeypatch.setenv(
            "CACHE_WORKER_URL", "https://cache-worker-production.example.com"
        )
        monkeypatch.setenv("CACHE_WORKER_JWT_SECRET", "production-secret-256-bit")
        monkeypatch.delenv("CACHE_WORKER_JWT_ENABLED", raising=False)

        client = get_cache_worker_client()

        assert client.base_url == "https://cache-worker-production.example.com"
        assert "Authorization" in client.headers

        # Verify token is valid
        token = client.headers["Authorization"].replace("Bearer ", "")
        decoded = jwt.decode(
            token,
            "production-secret-256-bit",
            algorithms=["HS256"],
            audience="cache-worker",
            options={"verify_exp": False},
        )
        assert decoded["sub"] == "aegra-service"
