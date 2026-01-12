#!/usr/bin/env python3
"""
Aegra CLI - Command-line interface for running the Aegra server.

This module provides a CLI for starting the Aegra server without requiring
the full repository setup. Users can install aegra via pip and run:

    aegra dev --database-uri=postgresql+asyncpg://user:password@host:port/db
    aegra up --database-uri=postgresql+asyncpg://user:password@host:port/db
"""

import logging
import os
import sys
from pathlib import Path

import click
import structlog
import uvicorn
from dotenv import load_dotenv

from .utils.setup_logging import get_logging_config, setup_logging


def _configure_environment(
    database_uri: str,
    auth_type: str = "noop",
    host: str = "0.0.0.0",
    port: int = 8000,
    config: str | None = None,
    log_level: str = "INFO",
) -> None:
    """Configure environment variables for Aegra."""
    os.environ["DATABASE_URL"] = database_uri
    os.environ["AUTH_TYPE"] = auth_type
    os.environ["HOST"] = host
    os.environ["PORT"] = str(port)
    os.environ["LOG_LEVEL"] = log_level

    if config:
        os.environ["AEGRA_CONFIG"] = config


def _configure_logging(level: str = "INFO") -> None:
    """Configure logging for the CLI."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    # Disable uvicorn default logging (we use structlog)
    logging.getLogger("uvicorn.error").disabled = True
    logging.getLogger("uvicorn.access").disabled = True

    # Ensure our package loggers are at least at the configured level
    logging.getLogger("agent_server").setLevel(log_level)
    logging.getLogger("src.agent_server").setLevel(log_level)
    logging.getLogger("aegra").setLevel(log_level)


def _add_graphs_to_path() -> None:
    """Add graphs directory to Python path if it exists."""
    cwd = Path.cwd()
    graphs_dir = cwd / "graphs"
    if graphs_dir.exists() and str(graphs_dir) not in sys.path:
        sys.path.insert(0, str(graphs_dir))


def _print_startup_banner(host: str, port: int, reload: bool) -> None:
    """Print startup information."""
    setup_logging()
    logger = structlog.get_logger()

    mode = "development" if reload else "production"
    logger.info(f"🚀 Starting Aegra in {mode} mode...")
    logger.info(f"🔐 Auth Type: {os.getenv('AUTH_TYPE', 'noop')}")
    logger.info(f"🗄️  Database: {os.getenv('DATABASE_URL', 'not set')}")
    logger.info(f"📍 Server: http://{host}:{port}")
    logger.info(f"📊 API docs: http://{host}:{port}/docs")

    config_path = os.getenv("AEGRA_CONFIG")
    if config_path:
        logger.info(f"📁 Config: {config_path}")


@click.group()
@click.version_option(package_name="aegra")
def cli() -> None:
    """Aegra - Open Source LangGraph Platform Alternative.

    Self-hosted AI agent backend with FastAPI and PostgreSQL.
    Zero vendor lock-in, full control over your agent infrastructure.

    \b
    Examples:
        aegra dev --database-uri=postgresql+asyncpg://user:pass@localhost:5432/db
        aegra up --database-uri=postgresql+asyncpg://user:pass@localhost:5432/db
    """
    pass


@cli.command()
@click.option(
    "--database-uri",
    "-d",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL database URI (e.g., postgresql+asyncpg://user:pass@host:port/db)",
)
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",  # nosec B104 - required for container/network access
    show_default=True,
    help="Host to bind the server to",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    show_default=True,
    help="Port to bind the server to",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to aegra.json or langgraph.json config file",
)
@click.option(
    "--auth-type",
    default="noop",
    show_default=True,
    type=click.Choice(["noop", "custom"]),
    help="Authentication type",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Logging level",
)
@click.option(
    "--no-reload",
    is_flag=True,
    default=False,
    help="Disable auto-reload (enabled by default in dev mode)",
)
def dev(
    database_uri: str,
    host: str,
    port: int,
    config: Path | None,
    auth_type: str,
    log_level: str,
    no_reload: bool,
) -> None:
    """Start Aegra in development mode with auto-reload.

    This command starts the server with hot-reloading enabled,
    suitable for local development and testing.

    \b
    Example:
        aegra dev --database-uri=postgresql+asyncpg://user:pass@localhost:5432/db
    """
    load_dotenv()
    _add_graphs_to_path()

    config_path = str(config) if config else None
    _configure_environment(
        database_uri=database_uri,
        auth_type=auth_type,
        host=host,
        port=port,
        config=config_path,
        log_level=log_level,
    )

    reload = not no_reload
    _configure_logging(log_level)
    _print_startup_banner(host, port, reload)

    uvicorn.run(
        "agent_server.main:app",
        host=host,
        port=port,
        reload=reload,
        access_log=False,
        log_config=get_logging_config(),
    )


@cli.command()
@click.option(
    "--database-uri",
    "-d",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL database URI (e.g., postgresql+asyncpg://user:pass@host:port/db)",
)
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",  # nosec B104 - required for container/network access
    show_default=True,
    help="Host to bind the server to",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    show_default=True,
    help="Port to bind the server to",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to aegra.json or langgraph.json config file",
)
@click.option(
    "--auth-type",
    default="noop",
    show_default=True,
    type=click.Choice(["noop", "custom"]),
    help="Authentication type",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Logging level",
)
@click.option(
    "--workers",
    "-w",
    default=1,
    show_default=True,
    help="Number of worker processes",
)
def up(
    database_uri: str,
    host: str,
    port: int,
    config: Path | None,
    auth_type: str,
    log_level: str,
    workers: int,
) -> None:
    """Start Aegra in production mode.

    This command starts the server without hot-reloading,
    suitable for production deployments.

    \b
    Example:
        aegra up --database-uri=postgresql+asyncpg://user:pass@localhost:5432/db
        aegra up -d postgresql+asyncpg://user:pass@host:5432/db --workers 4
    """
    load_dotenv()
    _add_graphs_to_path()

    config_path = str(config) if config else None
    _configure_environment(
        database_uri=database_uri,
        auth_type=auth_type,
        host=host,
        port=port,
        config=config_path,
        log_level=log_level,
    )

    _configure_logging(log_level)
    _print_startup_banner(host, port, reload=False)

    uvicorn.run(
        "agent_server.main:app",
        host=host,
        port=port,
        reload=False,
        workers=workers,
        access_log=False,
        log_config=get_logging_config(),
    )


@cli.command()
@click.option(
    "--database-uri",
    "-d",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL database URI (e.g., postgresql+asyncpg://user:pass@host:port/db)",
)
@click.argument("action", type=click.Choice(["upgrade", "current", "history"]))
def db(database_uri: str, action: str) -> None:
    """Database migration commands.

    \b
    Actions:
        upgrade  - Apply all pending migrations
        current  - Show current migration revision
        history  - Show migration history

    \b
    Example:
        aegra db --database-uri=postgresql+asyncpg://user:pass@localhost:5432/db upgrade
    """
    import subprocess

    os.environ["DATABASE_URL"] = database_uri

    # Find the scripts/migrate.py relative to the package
    package_dir = Path(__file__).parent.parent.parent
    migrate_script = package_dir / "scripts" / "migrate.py"

    if migrate_script.exists():
        subprocess.run([sys.executable, str(migrate_script), action], check=True)
    else:
        # Fallback: Try alembic directly
        click.echo("Running alembic migrations...")
        subprocess.run(["alembic", action], check=True)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
