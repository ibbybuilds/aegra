import logging
import logging.config
import sys
from typing import Any

import structlog
import structlog.typing

from aegra_api.settings import settings


def get_logging_config() -> dict[str, Any]:
    """Return a unified logging config dict for structlog + stdlib integration.

    Uses string references for streams (e.g., "ext://sys.stdout") to avoid
    the multiprocessing pickling error on Windows.
    """
    env_mode = settings.app.ENV_MODE
    log_level = settings.app.LOG_LEVEL

    # Determine mode-specific processors and renderer.
    #
    # Production: format_exc_info converts exc_info into a traceback string
    # because JSONRenderer cannot render exceptions on its own.
    #
    # Dev: ConsoleRenderer handles exc_info internally via its
    # exception_formatter, so format_exc_info must be excluded (it would
    # convert exceptions to plain strings before ConsoleRenderer sees them,
    # killing pretty traceback rendering).
    final_renderer: structlog.typing.Processor
    if env_mode in ("LOCAL", "DEVELOPMENT"):
        # RichTracebackFormatter uses Unicode box-drawing characters that
        # Windows cp1252 console encoding cannot render. Use plain_traceback
        # on Windows to avoid UnicodeEncodeError through colorama.
        if sys.platform == "win32":
            exception_formatter = structlog.dev.plain_traceback
        else:
            exception_formatter = structlog.dev.RichTracebackFormatter(
                show_locals=False,
                max_frames=10,
            )
        final_renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            pad_level=True,
            exception_formatter=exception_formatter,
        )
        mode_processors: list[Any] = []
    else:
        final_renderer = structlog.processors.JSONRenderer()
        mode_processors = [structlog.processors.format_exc_info]

    # Shared processors used by BOTH structlog and stdlib (via foreign_pre_chain).
    #
    # Ordering constraints:
    #   - merge_contextvars must be FIRST so request-scoped context
    #     (request_id, run_id, etc.) is visible to all subsequent processors
    #   - format_exc_info (production only) must come after StackInfoRenderer
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        *mode_processors,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.UnicodeDecoder(),
    ]

    return {
        "version": 1,
        # Keep library loggers (uvicorn, httpx, etc.) alive
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "structlog.stdlib.ProcessorFormatter",
                # remove_processors_meta strips internal keys before rendering
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    final_renderer,
                ],
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "formatter": "default",
                # String reference defers sys.stdout lookup until the config
                # is loaded in the child process (avoids pickling error).
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
            },
            "uvicorn.access": {
                "level": "WARNING",
            },
        },
    }


def setup_logging() -> None:
    """Configure both standard logging and structlog. Call once at startup."""
    config = get_logging_config()

    logging.config.dictConfig(config)

    # Uvicorn installs its own handlers on startup; clear them so all logs
    # go through our structlog formatter instead.
    for name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    # Silence overly chatty libraries
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

    # Route structlog through the stdlib logging system we just configured.
    shared_processors = config["formatters"]["default"]["foreign_pre_chain"]
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
