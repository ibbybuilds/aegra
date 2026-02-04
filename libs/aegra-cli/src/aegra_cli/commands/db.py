"""Database migration commands for Aegra."""

import subprocess
import sys

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


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

    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Database upgraded successfully![/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Alembic upgrade failed "
                f"with exit code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] Alembic is not installed.\n"
            "Install it with: [cyan]pip install alembic[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)


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

    cmd = [sys.executable, "-m", "alembic", "downgrade", revision]
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Database downgraded successfully![/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Alembic downgrade failed "
                f"with exit code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] Alembic is not installed.\n"
            "Install it with: [cyan]pip install alembic[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)


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

    cmd = [sys.executable, "-m", "alembic", "current"]
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Current revision displayed above.[/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Alembic current failed "
                f"with exit code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] Alembic is not installed.\n"
            "Install it with: [cyan]pip install alembic[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)


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

    cmd = [sys.executable, "-m", "alembic", "history"]
    if verbose:
        cmd.append("--verbose")
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Migration history displayed above.[/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Alembic history failed "
                f"with exit code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] Alembic is not installed.\n"
            "Install it with: [cyan]pip install alembic[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)
