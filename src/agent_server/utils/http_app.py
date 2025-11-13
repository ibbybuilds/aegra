"""Helpers for mounting/merging user-provided HTTP apps."""

from __future__ import annotations

import importlib
import os
from contextlib import asynccontextmanager
from importlib import util as importlib_util
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.middleware import Middleware

from .config_loader import get_http_config, resolve_config_path


def _import_attr(path: str) -> Any:
    if ":" not in path:
        raise ValueError(f"Invalid app import string '{path}'. Expected format 'module:attr'.")
    module_path, attr = path.split(":", 1)
    # Support relative module paths (e.g., "./src/api/app.py:app") by resolving
    # them relative to the configuration file.
    if module_path.startswith("." + os.sep) or module_path.startswith("./"):
        config_path = resolve_config_path()
        module_file = (config_path.parent / Path(module_path)).resolve()
        spec = importlib_util.spec_from_file_location(module_file.stem, module_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {module_file}")
        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_path)
    target: Any = module
    for part in attr.split("."):
        target = getattr(target, part)
    return target


def _merge_lifespans(base_app: FastAPI, user_app: FastAPI) -> None:
    base_lifespan = base_app.router.lifespan_context
    user_lifespan = user_app.router.lifespan_context

    if user_lifespan is None:
        return

    @asynccontextmanager
    async def combined(app):
        if base_lifespan:
            async with base_lifespan(app):
                async with user_lifespan(app):
                    yield
        else:
            async with user_lifespan(app):
                yield

    base_app.router.lifespan_context = combined


def _merge_fastapi_apps(base_app: FastAPI, user_app: FastAPI) -> None:
    """Merge routes/middleware/handlers from user_app into base_app."""

    # Include user routes first so existing Agent Protocol routes take precedence if overlapping.
    base_app.router.routes = user_app.router.routes + base_app.router.routes

    for middleware in getattr(user_app, "user_middleware", []) or []:
        if isinstance(middleware, Middleware):
            base_app.add_middleware(middleware.cls, **middleware.kwargs)
        else:
            # FastAPI stores middleware as objects with cls/options on older versions
            base_app.add_middleware(middleware.__class__, **getattr(middleware, "kwargs", {}))

    # Merge dependency overrides/exception handlers.
    base_app.dependency_overrides.update(user_app.dependency_overrides)
    for exc, handler in user_app.exception_handlers.items():
        if exc not in base_app.exception_handlers:
            base_app.exception_handlers[exc] = handler

    _merge_lifespans(base_app, user_app)


def attach_custom_http_app(app: FastAPI) -> FastAPI:
    """Attach user-provided FastAPI app if config/http.app is set."""

    http_config = get_http_config()
    if not http_config or not http_config.get("app"):
        return app

    custom = _import_attr(http_config["app"])
    if not isinstance(custom, FastAPI):
        raise ValueError("http.app must reference a FastAPI application instance")

    _merge_fastapi_apps(app, custom)

    return app


def apply_mount_prefix(app: FastAPI) -> FastAPI:
    http_config = get_http_config()
    prefix = None
    if http_config:
        prefix = http_config.get("mount_prefix")

    if not prefix or prefix in {"", "/"}:
        return app

    if not prefix.startswith("/") or prefix.endswith("/"):
        raise ValueError(
            f"Invalid mount_prefix '{prefix}': must start with '/' and cannot end with '/'."
        )

    wrapper = FastAPI()
    wrapper.mount(prefix, app)
    return wrapper
