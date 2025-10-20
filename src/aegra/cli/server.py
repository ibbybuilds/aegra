import logging
import os
import sys

import click
import uvicorn
from alembic import command as alembic_command
from dotenv import load_dotenv
from testcontainers.postgres import PostgresContainer

from aegra.cli.migrate import load_alembic_config

load_dotenv()


def configure_logging(level: str = "DEBUG"):
    """Configure root and app loggers to emit to stdout with formatting."""
    log_level = getattr(logging, level.upper(), logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    # Ensure our package/module loggers are at least at the configured level
    logging.getLogger("aegra.agent_server").setLevel(log_level)
    logging.getLogger("aegra.cli").setLevel(log_level)
    logging.getLogger("uvicorn.error").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)


@click.command()
@click.option("--port", type=int, default=2024, help="Port to run the server on")
@click.option("--host", type=str, default="127.0.0.1", help="Host to run the server on")
@click.option("--dev", is_flag=True, help="Development mode")
def serve(port, host, dev):
    """Start the server"""
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    os.environ.setdefault("AUTH_TYPE", "noop")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/aegra"
    )

    host = os.getenv("HOST", host)
    port = int(os.getenv("PORT", port))

    if dev:
        postgres = PostgresContainer("postgres:17", driver="asyncpg")
        postgres.start()
        os.environ["DATABASE_URL"] = postgres.get_connection_url()
        alembic_command.upgrade(load_alembic_config(), "head")

    click.echo("🚀 Starting Aegra...")
    click.echo(f"Auth Type: {os.getenv('AUTH_TYPE')}")
    click.echo(f"Database: {os.getenv('DATABASE_URL')}")
    click.echo(f"Server will be available at: http://{host}:{port}")
    click.echo(f"API docs will be available at: http://{host}:{port}/docs")
    click.echo("Test with: python test_sdk_integration.py")

    uvicorn.run(
        "aegra.agent_server.main:app",
        host=host,
        port=port,
        reload=dev,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "debug"),
    )

    if dev:
        postgres.stop()
