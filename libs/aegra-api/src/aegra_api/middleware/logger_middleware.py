import time
from typing import TypedDict, cast

import structlog
from asgi_correlation_id import correlation_id
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn._types import HTTPScope
from uvicorn.protocols.utils import get_path_with_query_string

from aegra_api.settings import settings

app_logger = structlog.stdlib.get_logger("app.app_logs")
access_logger = structlog.stdlib.get_logger("app.access_logs")


class AccessInfo(TypedDict, total=False):
    status_code: int
    start_time: float


class StructLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # If the request is not an HTTP request, we don't need to do anything special
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        http_scope = cast(HTTPScope, scope)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=correlation_id.get())

        info = AccessInfo()

        # Inner send function
        async def inner_send(message):
            if message.get("type") == "http.response.start":
                info["status_code"] = message.get("status", 500)
            await send(message)

        try:
            info["start_time"] = time.perf_counter_ns()
            await self.app(scope, receive, inner_send)
        except Exception as e:
            # Log the exception here, but re-raise so application-level
            # exception handlers (e.g. Agent Protocol formatter) can run.
            app_logger.exception(
                "An unhandled exception was caught by middleware; re-raising to allow app handlers to format response",
                exception_class=e.__class__.__name__,
                exc_info=e,
                stack_info=True,
            )
            raise
        finally:
            process_time = time.perf_counter_ns() - info["start_time"]
            status_code = info.get("status_code", 500)
            path: str = http_scope["path"]

            # Skip access log for excluded paths on successful responses.
            # Errors (4xx/5xx) are always logged, even for excluded paths.
            exclude_prefixes = settings.app.log_exclude_paths
            is_excluded = (
                status_code < 400 and exclude_prefixes and any(path.startswith(prefix) for prefix in exclude_prefixes)
            )

            if not is_excluded:
                client_info = http_scope.get("client")
                client_host, client_port = client_info if client_info else ("unknown", 0)
                http_method = http_scope["method"]
                http_version = http_scope["http_version"]
                url = get_path_with_query_string(http_scope)

                # Recreate the Uvicorn access log format, but add all parameters as structured information
                log_data = {
                    "url": str(url),
                    "status_code": status_code,
                    "method": http_method,
                    "version": http_version,
                }
                if settings.app.LOG_VERBOSITY == "verbose":
                    log_data["request_id"] = correlation_id.get()

                if 400 <= status_code < 500:
                    # Log as warning for client errors (4xx)
                    access_logger.warning(
                        f"""{client_host}:{client_port} - "{http_method} {path} HTTP/{http_version}" {status_code}""",
                        http=log_data,
                        network={"client": {"ip": client_host, "port": client_port}},
                        duration=process_time,
                    )
                elif 500 <= status_code < 600:
                    # Log as error for server errors (5xx)
                    access_logger.error(
                        f"""{client_host}:{client_port} - "{http_method} {path} HTTP/{http_version}" {status_code}""",
                        http=log_data,
                        network={"client": {"ip": client_host, "port": client_port}},
                        duration=process_time,
                    )
                else:
                    # Normal log for successful responses (2xx, 3xx)
                    access_logger.info(
                        f"""{client_host}:{client_port} - "{http_method} {path} HTTP/{http_version}" {status_code}""",
                        http=log_data,
                        network={"client": {"ip": client_host, "port": client_port}},
                        duration=process_time,
                    )
