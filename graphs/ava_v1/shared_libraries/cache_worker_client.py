"""Cache-worker client with JWT authentication support."""

import os
import time
from typing import Any

import httpx
import jwt


class CacheWorkerConfigError(Exception):
    """Raised when cache-worker configuration is invalid."""

    pass


def _is_jwt_enabled() -> bool:
    """Determine if JWT should be enabled.

    Enabled if:
    1. CACHE_WORKER_JWT_ENABLED=true, OR
    2. ENV_MODE in ['PRODUCTION', 'DEVELOPMENT'] (staging uses DEVELOPMENT)

    Disabled if:
    3. CACHE_WORKER_JWT_ENABLED=false, OR
    4. ENV_MODE=LOCAL
    """
    explicit = os.getenv("CACHE_WORKER_JWT_ENABLED", "").lower()
    if explicit in ["true", "false"]:
        return explicit == "true"

    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    return env_mode in ["PRODUCTION", "DEVELOPMENT"]


def _get_cache_worker_config() -> dict[str, Any]:
    """Get cache-worker configuration from environment variables.

    Returns:
        Dict with url, jwt_enabled, jwt_secret, jwt_issuer, jwt_audience

    Raises:
        CacheWorkerConfigError: If JWT enabled but secret missing
    """
    jwt_enabled = _is_jwt_enabled()
    jwt_secret = os.getenv("CACHE_WORKER_JWT_SECRET")

    if jwt_enabled and not jwt_secret:
        raise CacheWorkerConfigError(
            "CACHE_WORKER_JWT_SECRET is required when JWT authentication is enabled. "
            "Set CACHE_WORKER_JWT_ENABLED=false for local development or provide a secret."
        )

    return {
        "url": os.getenv("CACHE_WORKER_URL", "http://localhost:8080"),
        "jwt_enabled": jwt_enabled,
        "jwt_secret": jwt_secret,
        "jwt_issuer": os.getenv("CACHE_WORKER_JWT_ISSUER", "aegra"),
        "jwt_audience": os.getenv("CACHE_WORKER_JWT_AUDIENCE", "cache-worker"),
        "jwt_expiry_seconds": int(
            os.getenv("CACHE_WORKER_JWT_EXPIRY_SECONDS", "3600")
        ),
    }


def _generate_cache_worker_jwt() -> str:
    """Generate JWT token for cache-worker authentication.

    Uses HS256 algorithm with claims: iss, aud, iat, exp, sub
    Token expires after configured duration (default: 1 hour)

    Returns:
        JWT token string

    Raises:
        CacheWorkerConfigError: If configuration invalid
    """
    config = _get_cache_worker_config()

    current_time = int(time.time())
    payload = {
        "iss": config["jwt_issuer"],
        "aud": config["jwt_audience"],
        "iat": current_time,
        "exp": current_time + config["jwt_expiry_seconds"],
        "sub": "aegra-service",
    }

    token = jwt.encode(payload, config["jwt_secret"], algorithm="HS256")
    return token


def get_cache_worker_client() -> httpx.AsyncClient:
    """Create httpx.AsyncClient with JWT authentication if enabled.

    Returns AsyncClient configured with:
    - Authorization: Bearer <token> (if JWT enabled)
    - Base URL: CACHE_WORKER_URL
    - Default timeout: 30.0 seconds

    Usage:
        async with get_cache_worker_client() as client:
            response = await client.post("/v1/search", json=data)

    Returns:
        httpx.AsyncClient instance

    Raises:
        CacheWorkerConfigError: If JWT configuration invalid
    """
    config = _get_cache_worker_config()

    headers = {}
    if config["jwt_enabled"]:
        token = _generate_cache_worker_jwt()
        headers["Authorization"] = f"Bearer {token}"

    return httpx.AsyncClient(base_url=config["url"], headers=headers, timeout=30.0)
