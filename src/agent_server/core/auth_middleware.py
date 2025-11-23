"""
Authentication middleware integration for LangGraph Agent Server.

This module integrates LangGraph's authentication system with FastAPI
using Starlette's AuthenticationMiddleware.
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import structlog
from langgraph_sdk import Auth
from langgraph_sdk.auth.types import MinimalUserDict
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    BaseUser,
)
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from ..models.errors import AgentProtocolError

logger = structlog.getLogger(__name__)


class LangGraphUser(BaseUser):
    """
    User wrapper that implements Starlette's BaseUser interface
    while preserving LangGraph auth data.
    """

    def __init__(self, user_data: Auth.types.MinimalUserDict):
        self._user_data = user_data

    @property
    def identity(self) -> str:
        return self._user_data["identity"]

    @property
    def is_authenticated(self) -> bool:
        return self._user_data.get("is_authenticated", True)

    @property
    def display_name(self) -> str:
        return self._user_data.get("display_name", self.identity)

    def __getattr__(self, name: str) -> Any:
        """Allow access to any additional fields from auth data"""
        if name in self._user_data:
            return self._user_data[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def to_dict(self) -> MinimalUserDict:
        """Return the underlying user data dict"""
        return self._user_data.copy()


class LangGraphAuthBackend(AuthenticationBackend):
    """
    Authentication backend that uses LangGraph's auth system.

    This bridges LangGraph's @auth.authenticate handlers with
    Starlette's AuthenticationMiddleware.
    """

    def __init__(self) -> None:
        self.auth_instance = self._load_auth_instance()

    def _load_auth_instance(self) -> Auth | None:
        """Load the auth instance from auth.py"""
        try:
            # Import the auth instance from the project root auth.py
            auth_path = Path.cwd() / "auth.py"
            if not auth_path.exists():
                logger.warning(f"Auth file not found at {auth_path}")
                return None

            spec = importlib.util.spec_from_file_location("auth_module", str(auth_path))
            if spec is None or spec.loader is None:
                logger.error(f"Could not load auth module from {auth_path}")
                return None

            auth_module = importlib.util.module_from_spec(spec)
            sys.modules["auth_module"] = auth_module
            spec.loader.exec_module(auth_module)

            auth_instance = getattr(auth_module, "auth", None)
            if not isinstance(auth_instance, Auth):
                logger.error(f"No valid Auth instance found in {auth_path}")
                return None

            logger.info(f"Successfully loaded auth instance from {auth_path}")
            return auth_instance

        except Exception as e:
            logger.error(f"Error loading auth instance: {e}", exc_info=True)
            return None

    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, BaseUser] | None:
        """
        Authenticate request using LangGraph's auth system.

        Args:
            conn: HTTP connection containing request headers

        Returns:
            Tuple of (credentials, user) if authenticated, None otherwise

        Raises:
            AuthenticationError: If authentication fails
        """
        if self.auth_instance is None:
            logger.warning("No auth instance available, skipping authentication")
            return None

        if self.auth_instance._authenticate_handler is None:
            logger.warning(
                "No authenticate handler configured, skipping authentication"
            )
            return None

        try:
            # Convert headers to dict format expected by LangGraph
            headers = {
                key.decode() if isinstance(key, bytes) else key: value.decode()
                if isinstance(value, bytes)
                else value
                for key, value in conn.headers.items()
            }

            # Call LangGraph's authenticate handler
            user_data = await self.auth_instance._authenticate_handler(headers)

            if not user_data or not isinstance(user_data, dict):
                raise AuthenticationError(
                    "Invalid user data returned from auth handler"
                )

            if "identity" not in user_data:
                raise AuthenticationError("Auth handler must return 'identity' field")

            # Extract permissions for credentials
            permissions = user_data.get("permissions", [])
            if isinstance(permissions, str):
                permissions = [permissions]

            # Create Starlette-compatible user and credentials
            credentials = AuthCredentials(permissions)
            user = LangGraphUser(user_data)

            logger.debug(f"Successfully authenticated user: {user.identity}")
            return credentials, user

        except Auth.exceptions.HTTPException as e:
            logger.warning(f"Authentication failed: {e.detail}")
            raise AuthenticationError(e.detail) from e

        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}", exc_info=True)
            raise AuthenticationError("Authentication system error") from e


def get_auth_backend() -> AuthenticationBackend:
    """
    Get authentication backend based on AUTH_TYPE environment variable.

    Returns:
        AuthenticationBackend instance
    """
    auth_type = os.getenv("AUTH_TYPE", "noop").lower()

    if auth_type in ["noop", "custom"]:
        logger.info(f"Using LangGraph auth backend with type: {auth_type}")
        return LangGraphAuthBackend()
    else:
        logger.warning(f"Unknown AUTH_TYPE: {auth_type}, using noop")
        return LangGraphAuthBackend()


def on_auth_error(conn: HTTPConnection, exc: AuthenticationError) -> JSONResponse:
    """
    Handle authentication errors in Agent Protocol format.

    Args:
        conn: HTTP connection
        exc: Authentication error

    Returns:
        JSON response with Agent Protocol error format
    """
    logger.warning(f"Authentication error for {conn.url}: {exc}")

    return JSONResponse(
        status_code=401,
        content=AgentProtocolError(
            error="unauthorized",
            message=str(exc),
            details={"authentication_required": True},
        ).model_dump(),
    )
