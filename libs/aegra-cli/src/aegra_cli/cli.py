"""Aegra CLI - Command-line interface for managing self-hosted agent deployments."""

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aegra_cli import __version__
from aegra_cli.commands import db, init

console = Console()

# Attempt to get aegra-api version
try:
    from aegra_api import __version__ as api_version
except ImportError:
    api_version = "not installed"


@click.group()
@click.version_option(version=__version__, prog_name="aegra-cli")
def cli():
    """Aegra CLI - Manage your self-hosted agent deployments.

    Aegra is an open-source, self-hosted alternative to LangGraph Platform.
    Use this CLI to run development servers, manage Docker services, and more.
    """
    pass


@cli.command()
def version():
    """Show version information for aegra-cli and aegra-api."""
    table = Table(title="Aegra Version Information", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="bold")
    table.add_column("Version", style="green")

    table.add_row("aegra-cli", __version__)
    table.add_row("aegra-api", api_version)

    console.print()
    console.print(table)
    console.print()


@cli.command()
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind the server to.",
    show_default=True,
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="Port to bind the server to.",
    show_default=True,
)
@click.option(
    "--app",
    default="aegra_api.main:app",
    help="Application import path.",
    show_default=True,
)
def dev(host: str, port: int, app: str):
    """Run the development server with hot reload.

    Starts uvicorn with --reload flag for development.
    The server will automatically restart when code changes are detected.
    """
    console.print(
        Panel(
            f"[bold green]Starting Aegra development server[/bold green]\n\n"
            f"[cyan]Host:[/cyan] {host}\n"
            f"[cyan]Port:[/cyan] {port}\n"
            f"[cyan]App:[/cyan] {app}\n\n"
            f"[dim]Press Ctrl+C to stop the server[/dim]",
            title="[bold]Aegra Dev Server[/bold]",
            border_style="green",
        )
    )

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        app,
        "--host",
        host,
        "--port",
        str(port),
        "--reload",
    ]

    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] uvicorn is not installed.\n"
            "Install it with: [cyan]pip install uvicorn[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user.[/yellow]")
        sys.exit(0)


@cli.command()
@click.option(
    "--file",
    "-f",
    "compose_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to docker-compose.yml file.",
)
@click.option(
    "--build",
    is_flag=True,
    default=False,
    help="Build images before starting containers.",
)
@click.argument("services", nargs=-1)
def up(compose_file: Path | None, build: bool, services: tuple[str, ...]):
    """Start services with Docker Compose.

    Runs 'docker compose up -d' to start services in detached mode.
    Optionally specify specific services to start.

    Examples:

        aegra up                    # Start all services

        aegra up postgres           # Start only postgres

        aegra up --build            # Build and start all services

        aegra up -f ./docker-compose.prod.yml
    """
    console.print(
        Panel(
            "[bold green]Starting Aegra services with Docker Compose[/bold green]",
            title="[bold]Aegra Up[/bold]",
            border_style="green",
        )
    )

    cmd = ["docker", "compose"]

    if compose_file:
        cmd.extend(["-f", str(compose_file)])

    cmd.append("up")
    cmd.append("-d")

    if build:
        cmd.append("--build")

    if services:
        cmd.extend(services)
        console.print(f"[cyan]Services:[/cyan] {', '.join(services)}")
    else:
        console.print("[cyan]Services:[/cyan] all")

    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Services started successfully![/bold green]")
            console.print("[dim]Use 'aegra down' to stop services[/dim]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Docker Compose exited with code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] docker is not installed or not in PATH.\n"
            "Please install Docker Desktop or Docker Engine."
        )
        sys.exit(1)


@cli.command()
@click.option(
    "--file",
    "-f",
    "compose_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to docker-compose.yml file.",
)
@click.option(
    "--volumes",
    "-v",
    is_flag=True,
    default=False,
    help="Remove named volumes declared in the compose file.",
)
@click.argument("services", nargs=-1)
def down(compose_file: Path | None, volumes: bool, services: tuple[str, ...]):
    """Stop services with Docker Compose.

    Runs 'docker compose down' to stop and remove containers.

    Examples:

        aegra down                  # Stop all services

        aegra down postgres         # Stop only postgres

        aegra down -v               # Stop and remove volumes

        aegra down -f ./docker-compose.prod.yml
    """
    console.print(
        Panel(
            "[bold yellow]Stopping Aegra services with Docker Compose[/bold yellow]",
            title="[bold]Aegra Down[/bold]",
            border_style="yellow",
        )
    )

    cmd = ["docker", "compose"]

    if compose_file:
        cmd.extend(["-f", str(compose_file)])

    cmd.append("down")

    if volumes:
        cmd.append("-v")
        console.print("[yellow]Warning:[/yellow] Removing volumes - data will be lost!")

    if services:
        cmd.extend(services)
        console.print(f"[cyan]Services:[/cyan] {', '.join(services)}")
    else:
        console.print("[cyan]Services:[/cyan] all")

    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            console.print("\n[bold green]Services stopped successfully![/bold green]")
        else:
            console.print(
                f"\n[bold red]Error:[/bold red] Docker Compose exited with code {result.returncode}"
            )
        sys.exit(result.returncode)
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] docker is not installed or not in PATH.\n"
            "Please install Docker Desktop or Docker Engine."
        )
        sys.exit(1)


# Register command groups and commands from the commands package
cli.add_command(db)
cli.add_command(init)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
