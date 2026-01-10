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
AUTH_TYPE = os.getenv("AUTH_TYPE", "noop").lower()

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

    # JWT 配置
    from jose import JWTError, jwt
    JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    @auth.authenticate
    async def authenticate(headers: dict[str, str]) -> Auth.types.MinimalUserDict:
        """
        JWT authentication handler - 集成你的 quantitative_strategy_agent 认证逻辑
        
        允许无 token 请求通过（返回匿名用户），具体端点自己决定是否需要认证。
        这样 /auth/login, /auth/register 等公开端点可以正常访问。
        """
        # Extract authorization header
        authorization = (
            headers.get("authorization")
            or headers.get("Authorization")
            or headers.get(b"authorization")
            or headers.get(b"Authorization")
        )

        # Handle bytes headers
        if isinstance(authorization, bytes):
            authorization = authorization.decode("utf-8")

        # 没有 token 时返回匿名用户（允许公开端点访问）
        if not authorization:
            return {
                "identity": "anonymous",
                "display_name": "Anonymous User",
                "is_authenticated": False,  # 标记为未认证
            }

        # Parse Bearer token
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise Auth.exceptions.HTTPException(
                    status_code=401,
                    detail="Invalid authentication scheme. Expected 'Bearer <token>'"
                )
        except ValueError:
            raise Auth.exceptions.HTTPException(
                status_code=401,
                detail="Invalid authorization header format. Expected 'Bearer <token>'"
            )

        # Validate JWT token
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            email = payload.get("email")
            plan = payload.get("plan", "free")

            if not user_id:
                raise Auth.exceptions.HTTPException(
                    status_code=401,
                    detail="Invalid token payload: missing 'sub' field"
                )

            # Return user information
            return {
                "identity": user_id,
                "is_authenticated": True,
                "email": email,
                "subscription_plan": plan,
            }

        except JWTError as e:
            logger.warning(f"JWT validation failed: {str(e)}")
            raise Auth.exceptions.HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}"
            )

    @auth.on
    async def authorize(
        ctx: Auth.types.AuthContext, value: dict[str, Any]
    ) -> dict[str, Any]:
        """
        资源访问控制 - 确保用户只能访问自己的资源
        """
        try:
            # Get user identity from authentication context
            user_id = ctx.user.identity

            if not user_id:
                logger.error("Missing user identity in auth context")
                raise Auth.exceptions.HTTPException(
                    status_code=401, detail="Invalid user identity"
                )

            # Create owner filter for resource access control
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
