"""Route merging utilities for combining custom apps with Aegra core routes"""

import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from starlette.applications import Starlette
from starlette.routing import BaseRoute, Mount

if TYPE_CHECKING:
    from fastapi import APIRouter

logger = structlog.get_logger(__name__)


def merge_routes(
    user_app: Starlette,
    unshadowable_routes: list[BaseRoute],
    shadowable_routes: list[BaseRoute],
    protected_mount: Mount,
) -> Starlette:
    """Merge user app routes with Aegra core routes following priority order.

    Route priority:
    1. Unshadowable routes (health, docs, openapi) - always accessible
    2. User custom routes - can override shadowable routes
    3. Shadowable routes (root, info) - can be overridden by custom routes
    4. Protected core API mount (assistants, threads, runs, store) - mounted last

    Args:
        user_app: User's FastAPI/Starlette application
        unshadowable_routes: Routes that cannot be overridden (health, docs)
        shadowable_routes: Routes that can be overridden (root, info)
        protected_mount: Mount containing protected core API routes

    Returns:
        Modified user_app with merged routes
    """
    # Extract custom routes from user app
    custom_routes = list(user_app.routes)

    # Log custom route paths for debugging
    custom_paths = [
        getattr(route, "path", None)
        for route in custom_routes
        if hasattr(route, "path")
    ]
    logger.info(f"Custom route paths: {custom_paths}")

    # Merge routes in priority order
    user_app.router.routes = (
        unshadowable_routes + custom_routes + shadowable_routes + [protected_mount]
    )

    return user_app


def merge_lifespans(user_app: Starlette, core_lifespan: Callable) -> Starlette:
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


def merge_exception_handlers(
    user_app: Starlette, core_exception_handlers: dict[type, Callable]
) -> Starlette:
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


def update_openapi_spec(
    user_app: Starlette, core_routers: list["APIRouter"] | None = None
) -> None:
    """Update OpenAPI spec if user app is FastAPI.

    When a custom FastAPI app is merged with Aegra core routes, the core routes
    (which are added as Starlette Route/Mount objects) won't appear in FastAPI's
    OpenAPI spec generation. This function includes the core APIRouters so they
    appear in the generated OpenAPI spec.

    Args:
        user_app: User's FastAPI/Starlette application
        core_routers: List of Aegra core APIRouters to include in OpenAPI spec
    """
    if "fastapi" in sys.modules:
        from fastapi import FastAPI

        if isinstance(user_app, FastAPI):
            # Include core routers in the FastAPI app for OpenAPI spec generation
            # These routes are already mounted via merge_routes, but FastAPI's
            # OpenAPI generator only picks up routes added via include_router
            if core_routers:
                for router in core_routers:
                    user_app.include_router(router)
                logger.info(
                    "Core routers included in FastAPI app for OpenAPI spec generation",
                    router_count=len(core_routers),
                )
            logger.info(
                "Custom FastAPI app detected - OpenAPI spec will include custom routes"
            )
