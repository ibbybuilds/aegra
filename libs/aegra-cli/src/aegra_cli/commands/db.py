# NOTE: This module is intentionally retained but not registered on the CLI.
# The db commands were removed in v0.5.x because migrations run automatically
# on server startup. This file may be re-added when manual migration control
# is needed (e.g., for rolling deployments with Redis-based worker architecture).
"""Database migration commands for Aegra.

Uses alembic's Python API directly (instead of subprocess) so that
script_location is resolved relative to the ini file — not the CWD.
"""

import sys
from collections.abc import Callable
from io import StringIO
from pathlib import Path

import click
import structlog
from aegra_api.core.migrations import get_alembic_config
from alembic import command
from alembic.util import CommandError
from rich.console import Console
from rich.panel import Panel
from sqlalchemy.exc import SQLAlchemyError

from aegra_cli.env import load_env_file

console = Console()
logger = structlog.get_logger(__name__)


def _run_alembic(
    operation: str,
    fn: Callable[[], None],
    *,
    success_msg: str,
    error_prefix: str,
) -> None:
    """Run an alembic command with standard output handling.

    Args:
        operation: Description of the operation for display
        fn: Callable that invokes the alembic command
        success_msg: Message to display on success
        error_prefix: Prefix for error message
    """
    try:
        fn()
        console.print(f"\n[bold green]{success_msg}[/bold green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)
    except (SQLAlchemyError, CommandError) as e:
        logger.debug("Alembic operation failed", operation=operation, error=str(e))
        console.print(f"\n[bold red]Error:[/bold red] {error_prefix} failed.")
        sys.exit(1)
    except Exception:
        logger.debug(
            "Unexpected error during alembic operation",
            operation=operation,
            exc_info=True,
        )
        console.print(f"\n[bold red]Error:[/bold red] {error_prefix} failed.")
        sys.exit(1)


@click.group()
@click.option(
    "--env-file",
    "-e",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to .env file (default: .env in current directory).",
)
def db(env_file: str | None) -> None:
    """Database migration commands.

    Manage database migrations using Alembic.
    These commands are wrappers around common Alembic operations.
    """
    env_path = Path(env_file) if env_file else None
    load_env_file(env_path)


@db.command()
def upgrade() -> None:
    """Apply all pending migrations.

    Runs 'alembic upgrade head' to apply all pending migrations
    and bring the database schema up to date.

    Example:

        aegra db upgrade
    """
    console.print(
        Panel(
            "[bold green]Upgrading database to latest migration[/bold green]",
            title="[bold]Database Upgrade[/bold]",
            border_style="green",
        )
    )

    cfg = get_alembic_config()

    def run() -> None:
        command.upgrade(cfg, "head")

    _run_alembic(
        "upgrade",
        run,
        success_msg="Database upgraded successfully!",
        error_prefix="Alembic upgrade",
    )


@db.command()
@click.argument("revision", default="-1")
def downgrade(revision: str) -> None:
    """Downgrade database to a previous revision.

    Runs 'alembic downgrade' with the specified revision.
    Use '-1' to downgrade by one revision, or specify a revision hash.

    Arguments:

        REVISION: Target revision (default: -1 for one step back)

    Examples:

        aegra db downgrade          # Downgrade by one revision

        aegra db downgrade -2       # Downgrade by two revisions

        aegra db downgrade base     # Downgrade to initial state

        aegra db downgrade abc123   # Downgrade to specific revision
    """
    console.print(
        Panel(
            f"[bold yellow]Downgrading database to revision: {revision}[/bold yellow]",
            title="[bold]Database Downgrade[/bold]",
            border_style="yellow",
        )
    )

    if revision == "base":
        console.print("[yellow]Warning:[/yellow] Downgrading to 'base' will remove all migrations!")

    cfg = get_alembic_config()

    def run() -> None:
        command.downgrade(cfg, revision)

    _run_alembic(
        "downgrade",
        run,
        success_msg="Database downgraded successfully!",
        error_prefix="Alembic downgrade",
    )


@db.command()
def current() -> None:
    """Show current migration version.

    Displays the current revision that the database is at.
    Useful for checking which migrations have been applied.

    Example:

        aegra db current
    """
    console.print(
        Panel(
            "[bold cyan]Checking current database revision[/bold cyan]",
            title="[bold]Database Current[/bold]",
            border_style="cyan",
        )
    )

    cfg = get_alembic_config()
    # Capture alembic output to stdout
    output = StringIO()
    cfg.print_stdout = output.write

    def run() -> None:
        command.current(cfg)

    _run_alembic(
        "current",
        run,
        success_msg="Current revision check complete.",
        error_prefix="Alembic current",
    )
    if output.getvalue():
        console.print(output.getvalue().strip())


@db.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed migration information.",
)
def history(verbose: bool) -> None:
    """Show migration history.

    Displays the list of migrations in the Alembic history.
    Use --verbose for more detailed information.

    Examples:

        aegra db history            # Show migration history

        aegra db history --verbose  # Show detailed history
    """
    console.print(
        Panel(
            "[bold cyan]Displaying migration history[/bold cyan]",
            title="[bold]Database History[/bold]",
            border_style="cyan",
        )
    )

    cfg = get_alembic_config()
    output = StringIO()
    cfg.print_stdout = output.write

    def run() -> None:
        command.history(cfg, verbose=verbose)

    _run_alembic(
        "history",
        run,
        success_msg="Migration history check complete.",
        error_prefix="Alembic history",
    )
    if output.getvalue():
        console.print(output.getvalue().strip())
