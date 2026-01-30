"""
Authentication configuration for LangGraph Agent Server.

This module provides environment-based authentication switching between:
- noop: No authentication (allow all requests)
- custom: Custom authentication integration

Set AUTH_TYPE environment variable to choose authentication mode.
"""

import os
from typing import Any

import structlog
from langgraph_sdk import Auth

logger = structlog.getLogger(__name__)

# Initialize LangGraph Auth instance
auth = Auth()

# Get authentication type from environment
# Strip whitespace and inline comments (# comment)
AUTH_TYPE = os.getenv("AUTH_TYPE", "noop").split("#")[0].strip().lower()

if AUTH_TYPE == "noop":
    logger.info("Using noop authentication (no auth required)")

    @auth.authenticate
    async def authenticate(headers: dict[str, str]) -> Auth.types.MinimalUserDict:
        """No-op authentication that allows all requests."""
        _ = headers  # Suppress unused warning
        return {
            "identity": "anonymous",
            "display_name": "Anonymous User",
            "is_authenticated": True,
        }

    @auth.on
    async def authorize(
        ctx: Auth.types.AuthContext, value: dict[str, Any]
    ) -> dict[str, Any]:
        """No-op authorization that allows access to all resources."""
        _ = ctx, value  # Suppress unused warnings
        return {}  # Empty filter = no access restrictions

elif AUTH_TYPE == "custom":
    logger.info("Using custom JWT authentication")

    from src.agent_server.core.jwt_utils import (
        JWTAuthenticationError,
        JWTConfigurationError,
        verify_jwt_token,
    )

    # Issuer-based scope mapping (server-side enforcement)
    # This prevents services from self-assigning elevated privileges
    # Can be overridden via AEGRA_JWT_ISSUER_SCOPES env var for testing
    # Format: "issuer1:scope1,scope2;issuer2:scope3"
    def _get_issuer_scope_map() -> dict[str, list[str]]:
        """Get issuer-to-scopes mapping from environment or use defaults.

        Called dynamically to support test isolation.
        """
        env_mapping = os.getenv("AEGRA_JWT_ISSUER_SCOPES")
        if env_mapping is not None:
            # Empty string means no mappings (for tests)
            if not env_mapping:
                return {}

            # Parse environment variable: "issuer1:scope1,scope2;issuer2:scope3"
            result = {}
            for issuer_scopes in env_mapping.split(";"):
                if ":" in issuer_scopes:
                    issuer, scopes_str = issuer_scopes.split(":", 1)
                    result[issuer.strip()] = [s.strip() for s in scopes_str.split(",")]
            return result

        # Default production mapping (when env var not set)
        return {
            "conversation-relay": ["admin"],  # Full access to all operations
            "transcript-service": ["read:all"],  # Read-only access to all resources
        }

    @auth.authenticate
    async def authenticate(headers: dict[str, str]) -> Auth.types.MinimalUserDict:
        """
        JWT authentication handler.

        Extracts Bearer token from Authorization header, verifies JWT signature,
        and maps claims to user context. Uses LRU cache for <1ms latency.
        """
        # Extract authorization header (handle both string and bytes)
        authorization = (
            headers.get("authorization")
            or headers.get("Authorization")
            or headers.get(b"authorization")
            or headers.get(b"Authorization")
        )

        # Handle bytes headers
        if isinstance(authorization, bytes):
            authorization = authorization.decode("utf-8")

        if not authorization:
            logger.warning("Missing Authorization header")
            raise Auth.exceptions.HTTPException(
                status_code=401, detail="Authorization header required"
            )

        # Verify Bearer token format
        if not authorization.startswith("Bearer "):
            logger.warning(
                "Invalid authorization format", authorization_prefix=authorization[:20]
            )
            raise Auth.exceptions.HTTPException(
                status_code=401,
                detail="Invalid authorization format. Expected 'Bearer <token>'",
            )

        # Extract token (remove "Bearer " prefix)
        token = authorization[7:].strip()

        if not token:
            logger.warning("Empty token after Bearer prefix")
            raise Auth.exceptions.HTTPException(
                status_code=401, detail="Authorization token is empty"
            )

        # Verify and decode JWT token (uses LRU cache)
        try:
            payload = verify_jwt_token(token)

            # Get issuer from token for scope mapping
            issuer = payload.get("iss")

            # Map issuer to allowed scopes (server-side enforcement)
            # Scopes in the token are IGNORED - only server-defined scopes are used
            issuer_scope_map = _get_issuer_scope_map()
            allowed_scopes = issuer_scope_map.get(issuer, [])

            # Map JWT claims to MinimalUserDict
            user_dict: Auth.types.MinimalUserDict = {
                "identity": payload["sub"],  # Required: subject claim
                "is_authenticated": True,
                "permissions": allowed_scopes,  # Server-defined scopes, not from token
            }

            # Optional claims
            if "name" in payload:
                user_dict["display_name"] = payload["name"]
            if "email" in payload:
                user_dict["email"] = payload["email"]
            if "org" in payload:
                user_dict["org_id"] = payload["org"]

            logger.info(
                "JWT authentication successful",
                user_id=user_dict["identity"],
                issuer=issuer,
                permissions=allowed_scopes,
                org_id=user_dict.get("org_id"),
            )

            return user_dict

        except JWTConfigurationError as e:
            logger.error("JWT configuration error", error=str(e))
            raise Auth.exceptions.HTTPException(
                status_code=500, detail="Authentication system misconfigured"
            )
        except JWTAuthenticationError as e:
            logger.warning("JWT verification failed", error=str(e))
            raise Auth.exceptions.HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            logger.error("Unexpected authentication error", error=str(e), exc_info=True)
            raise Auth.exceptions.HTTPException(
                status_code=500, detail="Authentication system error"
            )

    @auth.on
    async def authorize(
        ctx: Auth.types.AuthContext, value: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Multi-tenant authorization with admin override support.

        Regular users: Can only access their own resources (user-scoped)
        Admin users: Can access all resources (scope-based: admin, read:all, write:all)
        """
        try:
            # Get user identity and permissions from authentication context
            user_id = ctx.user.identity
            permissions = ctx.user.get("permissions", [])

            if not user_id:
                logger.error("Missing user identity in auth context")
                raise Auth.exceptions.HTTPException(
                    status_code=401, detail="Invalid user identity"
                )

            # Check for admin/service-level permissions
            has_admin = "admin" in permissions
            has_read_all = "read:all" in permissions
            has_write_all = "write:all" in permissions

            if has_admin or has_read_all or has_write_all:
                # Service accounts with elevated permissions
                # No owner filtering - can access ALL resources
                logger.info(
                    "Admin access granted",
                    user_id=user_id,
                    permissions=permissions,
                )

                # Still set owner metadata for CREATE operations
                # (so created resources are attributed to the service)
                if value is not None:
                    metadata = value.setdefault("metadata", {})
                    if "owner" not in metadata:
                        metadata["owner"] = user_id

                return {}  # Empty filter = no restrictions

            # Regular users: user-scoped access only
            owner_filter = {"owner": user_id}

            # Add owner information to metadata for create/update operations
            metadata = value.setdefault("metadata", {})
            metadata.update(owner_filter)

            # Return filter for database operations
            return owner_filter

        except Auth.exceptions.HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authorization error: {e}", exc_info=True)
            raise Auth.exceptions.HTTPException(
                status_code=500, detail="Authorization system error"
            ) from e

else:
    raise ValueError(
        f"Unknown AUTH_TYPE: {AUTH_TYPE}. Supported values: 'noop', 'custom'"
    )
