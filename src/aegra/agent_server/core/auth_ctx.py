"""Lightweight context-var helpers for passing authenticated user info into LangGraph graphs.

Graph nodes can access the current request's authentication context by calling
`get_auth_ctx()`.  The server sets the context for the lifetime of a single run
(using an async context-manager) so the information is automatically scoped and
cleaned up.

We mirror the structure used by the vendored reference implementation so that
libraries expecting `Auth.types.BaseAuthContext` work unchanged.
"""

from __future__ import annotations

import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph_sdk import Auth  # type: ignore
from starlette.authentication import AuthCredentials, BaseUser

# Internal context-var storing the current auth context (or None when absent)
_AuthCtx: contextvars.ContextVar[Auth.types.BaseAuthContext | None] = (
    contextvars.ContextVar(  # type: ignore[attr-defined]
        "LangGraphAuthContext", default=None
    )
)


def get_auth_ctx() -> Auth.types.BaseAuthContext | None:  # type: ignore[attr-defined]
    """Return the current authentication context or ``None`` if not set."""
    return _AuthCtx.get()


@asynccontextmanager
async def with_auth_ctx(
    user: BaseUser | None,
    permissions: list[str] | AuthCredentials | None = None,
) -> AsyncIterator[None]:
    """Temporarily set the auth context for the duration of an async block.

    Parameters
    ----------
    user
        The authenticated user (or ``None`` for anonymous access).
    permissions
        Either a Starlette ``AuthCredentials`` instance or a list of permission
        strings.  ``None`` means no permissions.
    """
    # Normalize the permissions list
    scopes: list[str] = []
    if isinstance(permissions, AuthCredentials):
        scopes = list(permissions.scopes)
    elif isinstance(permissions, list):
        scopes = permissions

    if user is None and not scopes:
        token = _AuthCtx.set(None)
    else:
        token = _AuthCtx.set(
            Auth.types.BaseAuthContext(  # type: ignore[attr-defined]
                user=user, permissions=scopes
            )
        )
    try:
        yield
    finally:
        _AuthCtx.reset(token)
