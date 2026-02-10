"""Database migration commands for Aegra."""

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def _get_alembic_config_args() -> list[str]:
    """Get alembic CLI args to locate the correct config file.

    Resolution order:
    1. alembic.ini in CWD (repo development, Docker)
    2. Bundled with aegra_api package (pip install)

    Returns:
        List of extra CLI args (e.g. ["-c", "/path/to/alembic.ini"]) or empty list
    """
    # 1. CWD has alembic.ini - use default behavior
    if Path("alembic.ini").exists():
        return []

    # 2. Try to find from installed aegra-api package
    try:
        from aegra_api.core.migrations import find_alembic_ini

        ini_path = find_alembic_ini()
        return ["-c", str(ini_path)]
    except (ImportError, FileNotFoundError):
        return []


def _build_alembic_cmd(*args: str) -> list[str]:
    """Build a full alembic command with correct config path.

    Args:
        *args: Alembic subcommand and arguments (e.g. "upgrade", "head")

    Returns:
        Complete command list for subprocess.run
    """
    config_args = _get_alembic_config_args()
    return [sys.executable, "-m", "alembic"] + config_args + list(args)


def _run_alembic_cmd(cmd: list[str], success_msg: str, error_prefix: str) -> None:
    """Run an alembic command with standard output handling.

    Args:
        cmd: Command list for subprocess.run
        success_msg: Message to display on success
        error_prefix: Prefix for error message
    """
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print(f"\n[bold green]{success_msg}[/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] {error_prefix} "
                f"failed with exit code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] Alembic is not installed.\n"
            "Install it with: [cyan]pip install aegra-api[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)


@click.group()
def db():
    """Database migration commands.

    Manage database migrations using Alembic.
    These commands are wrappers around common Alembic operations.
    """
    pass


@db.command()
def upgrade():
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

    cmd = _build_alembic_cmd("upgrade", "head")
    _run_alembic_cmd(cmd, "Database upgraded successfully!", "Alembic upgrade")


@db.command()
@click.argument("revision", default="-1")
def downgrade(revision: str):
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

    cmd = _build_alembic_cmd("downgrade", revision)
    _run_alembic_cmd(cmd, "Database downgraded successfully!", "Alembic downgrade")


@db.command()
def current():
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

    cmd = _build_alembic_cmd("current")
    _run_alembic_cmd(cmd, "Current revision displayed above.", "Alembic current")


@db.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed migration information.",
)
def history(verbose: bool):
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

    args = ["history"]
    if verbose:
        args.append("--verbose")
    cmd = _build_alembic_cmd(*args)
    _run_alembic_cmd(cmd, "Migration history displayed above.", "Alembic history")
