"""JWT authentication utilities with aggressive caching for sub-1ms latency.

This module provides JWT verification with LRU caching to minimize latency
between conversation-relay and aegra. Uses HS256 (symmetric) algorithm with
shared secret.

Performance characteristics:
- Cache hit (80%+ expected): <0.5ms
- Cache miss: 3-5ms
- Cache size: 1000 entries (~0.5MB memory)
"""

import os
from functools import lru_cache
from typing import Any

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    MissingRequiredClaimError,
)


def _get_jwt_config() -> dict[str, Any]:
    """Get JWT configuration from environment variables.

    Reads environment variables each time to support testing with monkeypatch.
    """
    # Support both single issuer (AEGRA_JWT_ISSUER) and multiple issuers (AEGRA_JWT_ISSUERS)
    issuers_str = os.getenv("AEGRA_JWT_ISSUERS") or os.getenv("AEGRA_JWT_ISSUER")
    issuers = [iss.strip() for iss in issuers_str.split(",")] if issuers_str else []

    return {
        "algorithm": os.getenv("AEGRA_JWT_ALGORITHM", "HS256"),
        "secret": os.getenv("AEGRA_JWT_SECRET"),
        "issuers": issuers,  # List of trusted issuers
        "audience": os.getenv("AEGRA_JWT_AUDIENCE"),
        "verify_expiration": os.getenv("AEGRA_JWT_VERIFY_EXPIRATION", "true").lower() == "true",
        "leeway_seconds": int(os.getenv("AEGRA_JWT_LEEWAY_SECONDS", "30")),
    }


class JWTAuthenticationError(Exception):
    """Base exception for JWT authentication errors."""

    pass


class JWTConfigurationError(Exception):
    """Exception raised when JWT configuration is invalid."""

    pass


def validate_jwt_configuration() -> None:
    """Validate that required JWT configuration is present.

    Raises:
        JWTConfigurationError: If required configuration is missing.
    """
    config = _get_jwt_config()

    if not config["secret"]:
        raise JWTConfigurationError(
            "AEGRA_JWT_SECRET environment variable is required for JWT authentication"
        )
    if not config["issuers"]:
        raise JWTConfigurationError(
            "AEGRA_JWT_ISSUERS (or AEGRA_JWT_ISSUER) environment variable is required for JWT authentication"
        )
    if not config["audience"]:
        raise JWTConfigurationError(
            "AEGRA_JWT_AUDIENCE environment variable is required for JWT authentication"
        )


@lru_cache(maxsize=1000)
def _verify_and_decode_jwt_cached(token: str) -> dict[str, Any]:
    """Cached JWT verification for <1ms latency on cache hits.

    This function uses LRU caching to avoid repeated signature verification
    for the same token. Cache key is the token string itself.

    Args:
        token: Raw JWT token string (without "Bearer " prefix)

    Returns:
        Decoded JWT payload as dictionary

    Raises:
        JWTAuthenticationError: If token is invalid, expired, or malformed
    """
    try:
        # Verify configuration before attempting decode
        validate_jwt_configuration()

        # Get configuration
        config = _get_jwt_config()

        # Build verification options
        options = {
            "verify_signature": True,
            "verify_exp": config["verify_expiration"],
            "verify_iat": True,
            "verify_aud": True,
            "verify_iss": True,
        }

        # Decode and verify token (PyJWT accepts issuer as string or list)
        payload = jwt.decode(
            token,
            config["secret"],
            algorithms=[config["algorithm"]],
            audience=config["audience"],
            issuer=config["issuers"],  # List of trusted issuers
            options=options,
            leeway=config["leeway_seconds"],
        )

        # Verify required claims
        if "sub" not in payload:
            raise MissingRequiredClaimError("Token missing required 'sub' claim")

        return payload

    except ExpiredSignatureError as e:
        raise JWTAuthenticationError(f"Token expired: {e}")
    except InvalidSignatureError as e:
        raise JWTAuthenticationError(f"Invalid token signature: {e}")
    except InvalidIssuerError as e:
        raise JWTAuthenticationError(f"Invalid token issuer: {e}")
    except InvalidAudienceError as e:
        raise JWTAuthenticationError(f"Invalid token audience: {e}")
    except MissingRequiredClaimError as e:
        raise JWTAuthenticationError(f"Missing required claim: {e}")
    except DecodeError as e:
        raise JWTAuthenticationError(f"Failed to decode token: {e}")
    except JWTConfigurationError:
        raise
    except Exception as e:
        raise JWTAuthenticationError(f"Unexpected error verifying token: {e}")


def verify_jwt_token(token: str) -> dict[str, Any]:
    """Public API for JWT verification.

    Verifies and decodes a JWT token, using LRU cache for performance.

    Args:
        token: Raw JWT token string (without "Bearer " prefix)

    Returns:
        Decoded JWT payload with claims:
            - sub (str): Subject (user identifier) - REQUIRED
            - name (str): User display name - OPTIONAL
            - email (str): User email - OPTIONAL
            - org (str): Organization ID - OPTIONAL
            - scopes (list[str]): User permissions - OPTIONAL
            - iss (str): Issuer
            - aud (str): Audience
            - iat (int): Issued at timestamp
            - exp (int): Expiration timestamp

    Raises:
        JWTAuthenticationError: If token is invalid, expired, or malformed
        JWTConfigurationError: If JWT configuration is incomplete

    Example:
        >>> token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        >>> payload = verify_jwt_token(token)
        >>> print(payload["sub"])
        "user-123"
    """
    return _verify_and_decode_jwt_cached(token)


def clear_jwt_cache() -> None:
    """Clear the JWT verification cache.

    Useful for testing or when you need to force re-verification of all tokens.
    In production, this should rarely be needed as tokens naturally expire.
    """
    _verify_and_decode_jwt_cached.cache_clear()


def get_jwt_cache_info() -> dict[str, int]:
    """Get JWT cache statistics.

    Returns:
        Dictionary with cache statistics:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - maxsize: Maximum cache size
            - currsize: Current cache size
    """
    info = _verify_and_decode_jwt_cached.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize,
        "currsize": info.currsize,
    }
