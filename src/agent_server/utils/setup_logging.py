import logging
import logging.config
import os
from typing import Any

import structlog


def get_logging_config() -> dict[str, Any]:
    """
    Returns a unified logging configuration dictionary that uses structlog
    for consistent, structured logging across the application and Uvicorn.

    This configuration solves the multiprocessing "pickling" error on Windows
    by using string references for streams (e.g., "ext://sys.stdout").
    """
    # Determine log level from environment or set a default
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # These processors will be used by BOTH structlog and standard logging
    # to ensure consistent output for all logs.
    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        structlog.processors.TimeStamper(fmt="iso"),
        # This processor must be last in the shared chain to format positional args.
        structlog.stdlib.PositionalArgumentsFormatter(),
    ]

    # Determine the final renderer based on the environment
    # Use a colorful console renderer for local development, and JSON for production.
    if env_mode in ("LOCAL", "DEVELOPMENT"):
        final_renderer = structlog.dev.ConsoleRenderer(colors=True, pad_level=True)
    else:
        final_renderer = structlog.processors.JSONRenderer()

    return {
        "version": 1,
        "disable_existing_loggers": False,  # Important for library logging
        "formatters": {
            "default": {
                # Use structlog's formatter as the bridge
                "()": "structlog.stdlib.ProcessorFormatter",
                # The final processor is the renderer.
                "processor": final_renderer,
                # These processors are run on ANY log record, including those from Uvicorn.
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "formatter": "default",
                # IMPORTANT: Use the string reference to avoid the pickling error.
                # This defers the lookup of sys.stdout until the config is loaded
                # in the child process.
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Configure the root logger to catch everything
            "": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,  # Don't pass to other handlers
            },
            # Uvicorn's loggers will now inherit the root logger's settings,
            # ensuring they use the same handler and formatter.
            # We explicitly set their level here.
            "uvicorn.error": {
                "level": "INFO",
            },
            "uvicorn.access": {
                "level": "WARNING",
            },
        },
    }


def setup_logging():
    """
    Configures both standard logging and structlog based on the
    dictionary from get_logging_config(). This should be called
    once at application startup.
    """
    config = get_logging_config()

    # Configure the standard logging module
    logging.config.dictConfig(config)
    # Propagate uvicorn logs instead of letting uvicorn configure the format
    for name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    # Reconfigure log levels for some overly chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

    # Configure structlog to route its logs through the standard logging
    # system that we just configured.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            # Add shared processors to structlog's pipeline
            *config["formatters"]["default"]["foreign_pre_chain"],
            # Prepare the log record for the standard library's formatter
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
