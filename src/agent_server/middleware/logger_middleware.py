import os
import time
from typing import TypedDict

import structlog
from asgi_correlation_id import correlation_id
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.protocols.utils import get_path_with_query_string

app_logger = structlog.stdlib.get_logger("app.app_logs")
access_logger = structlog.stdlib.get_logger("app.access_logs")


class AccessInfo(TypedDict, total=False):
    status_code: int
    start_time: float


class StructLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # If the request is not an HTTP request, we don't need to do anything special
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=correlation_id.get())

        info = AccessInfo()

        # Inner send function
        async def inner_send(message):
            if message["type"] == "http.response.start":
                info["status_code"] = message["status"]
            await send(message)

        try:
            info["start_time"] = time.perf_counter_ns()
            await self.app(scope, receive, inner_send)
        except Exception as e:
            app_logger.exception(
                "An unhandled exception was caught by last resort middleware",
                exception_class=e.__class__.__name__,
                exc_info=e,
                stack_info=True,
            )
            info["status_code"] = 500
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred.",
                },
            )
            await response(scope, receive, send)
        finally:
            process_time = time.perf_counter_ns() - info["start_time"]
            client_host, client_port = scope["client"]
            http_method = scope["method"]
            http_version = scope["http_version"]
            url = get_path_with_query_string(scope)

            # Recreate the Uvicorn access log format, but add all parameters as structured information
            log_data = {
                "url": str(url),
                "status_code": info["status_code"],
                "method": http_method,
                "version": http_version,
            }
            if os.getenv("LOG_VERBOSITY", "standard").lower() == "verbose":
                log_data["request_id"] = correlation_id.get()

            status_code = info["status_code"]
            if 400 <= status_code < 500:
                # Log as warning for client errors (4xx)
                access_logger.warning(
                    f"""{client_host}:{client_port} - "{http_method} {scope["path"]} HTTP/{http_version}" {status_code}""",
                    http=log_data,
                    network={"client": {"ip": client_host, "port": client_port}},
                    duration=process_time,
                )
            elif 500 <= status_code < 600:
                # Log as error for server errors (5xx)
                access_logger.error(
                    f"""{client_host}:{client_port} - "{http_method} {scope["path"]} HTTP/{http_version}" {status_code}""",
                    http=log_data,
                    network={"client": {"ip": client_host, "port": client_port}},
                    duration=process_time,
                )
            else:
                # Normal log for successful responses (2xx, 3xx)
                access_logger.info(
                    f"""{client_host}:{client_port} - "{http_method} {scope["path"]} HTTP/{http_version}" {status_code}""",
                    http=log_data,
                    network={"client": {"ip": client_host, "port": client_port}},
                    duration=process_time,
                )
