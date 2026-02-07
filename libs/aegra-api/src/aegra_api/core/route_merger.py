"""Route merging utilities for combining custom apps with Aegra core routes"""

from collections.abc import Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

logger = structlog.get_logger(__name__)


def merge_lifespans(user_app: FastAPI, core_lifespan: Callable) -> FastAPI:
    """Merge user lifespan with Aegra's core lifespan.

    Both lifespans will run, with core lifespan wrapping user lifespan.
    This ensures Aegra's initialization (database, services) happens before
    user initialization, and cleanup happens in reverse order.

    Args:
        user_app: User's FastAPI/Starlette application
        core_lifespan: Aegra's core lifespan context manager

    Returns:
        Modified user_app with merged lifespan
    """
    user_lifespan = user_app.router.lifespan_context

    # Check for deprecated on_startup/on_shutdown handlers
    if user_app.router.on_startup or user_app.router.on_shutdown:
        raise ValueError(
            f"Cannot merge lifespans with on_startup or on_shutdown handlers. "
            f"Please use lifespan context manager instead. "
            f"Found: on_startup={user_app.router.on_startup}, "
            f"on_shutdown={user_app.router.on_shutdown}"
        )

    @asynccontextmanager
    async def combined_lifespan(app):
        async with core_lifespan(app):
            if user_lifespan:
                async with user_lifespan(app):
                    yield
            else:
                yield

    user_app.router.lifespan_context = combined_lifespan
    return user_app


def merge_exception_handlers(user_app: FastAPI, core_exception_handlers: dict[type, Callable]) -> FastAPI:
    """Merge core exception handlers with user exception handlers.

    Core handlers are added only if user hasn't defined a handler for that exception type.
    User handlers take precedence.

    Args:
        user_app: User's FastAPI/Starlette application
        core_exception_handlers: Aegra's core exception handlers

    Returns:
        Modified user_app with merged exception handlers
    """
    for exc_type, handler in core_exception_handlers.items():
        if exc_type not in user_app.exception_handlers:
            user_app.exception_handlers[exc_type] = handler
        else:
            logger.debug(f"User app overrides exception handler for {exc_type}")

    return user_app
