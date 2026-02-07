#!/usr/bin/env python3
"""
Server startup script for testing.

This script:
1. Sets up the environment
2. Starts the FastAPI server
3. Can be used for testing our LangGraph integration
"""

import asyncio
import logging
import sys
from pathlib import Path

# Fix for Windows: psycopg async requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
import uvicorn
from dotenv import load_dotenv

from aegra_api.settings import settings
from aegra_api.utils.setup_logging import get_logging_config, setup_logging

# Add graphs directory to Python path so imports can be resolved
current_dir = Path(__file__).parent
graphs_dir = current_dir / "graphs"
if str(graphs_dir) not in sys.path:
    sys.path.insert(0, str(graphs_dir))

setup_logging()
logger = structlog.get_logger()


def configure_logging(level: str = "DEBUG"):
    """Configure root and app loggers to emit to stdout with formatting."""
    log_level = getattr(logging, level, logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    logging.getLogger("uvicorn.error").disabled = True
    logging.getLogger("uvicorn.access").disabled = True

    # Ensure our package/module loggers are at least at the configured level
    logging.getLogger("aegra_api").setLevel(log_level)


def main():
    """Start the server"""
    configure_logging(settings.app.LOG_LEVEL)

    port = settings.app.PORT

    logger.info(f"🔐 Auth Type: {settings.app.AUTH_TYPE}")
    logger.info(f"🗄️  Database: {settings.db.database_url}")

    logger.info("🚀 Starting Aegra...")
    logger.info(f"📍 Server will be available at: http://localhost:{port}")
    logger.info(f"📊 API docs will be available at: http://localhost:{port}/docs")
    logger.info("🧪 Test with: python test_sdk_integration.py")

    uvicorn.run(
        "aegra_api.main:app",
        host=settings.app.HOST,
        port=port,
        reload=True,
        access_log=False,
        log_config=get_logging_config(),
        # Increase limits for file uploads with base64 encoding
        limit_concurrency=None,  # No limit on concurrent connections
        limit_max_requests=None,  # No limit on requests
        timeout_keep_alive=75,  # Keep connections alive longer
    )


if __name__ == "__main__":
    load_dotenv()
    main()
