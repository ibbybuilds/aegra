"""Aegra CLI - Command-line interface for managing self-hosted agent deployments."""

import signal
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aegra_cli import __version__
from aegra_cli.commands import db, init
from aegra_cli.utils.docker import ensure_postgres_running

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


def load_env_file(env_file: Path | None) -> Path | None:
    """Load environment variables from a .env file.

    Args:
        env_file: Path to .env file, or None to use default (.env in cwd)

    Returns:
        Path to the loaded .env file, or None if not found
    """
    import os

    # Determine which file to load
    if env_file is not None:
        target = env_file
    else:
        # Default: look for .env in current directory
        target = Path.cwd() / ".env"

    if not target.exists():
        return None

    # Load the .env file into environment
    # Simple parser - handles KEY=value format
    with open(target, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=value (handle = in value)
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                # Only set if not already in environment (env vars take precedence)
                if key and key not in os.environ:
                    os.environ[key] = value

    return target


def find_config_file() -> Path | None:
    """Find aegra.json or langgraph.json in current directory.

    Returns:
        Path to config file if found, None otherwise
    """
    # Check for aegra.json first
    aegra_config = Path.cwd() / "aegra.json"
    if aegra_config.exists():
        return aegra_config

    # Fallback to langgraph.json
    langgraph_config = Path.cwd() / "langgraph.json"
    if langgraph_config.exists():
        return langgraph_config

    return None


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
@click.option(
    "--config",
    "-c",
    "config_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to aegra.json config file (auto-discovered if not specified).",
)
@click.option(
    "--env-file",
    "-e",
    "env_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to .env file (default: .env in project directory).",
)
@click.option(
    "--no-db-check",
    is_flag=True,
    default=False,
    help="Skip automatic PostgreSQL/Docker check.",
)
@click.option(
    "--file",
    "-f",
    "compose_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to docker-compose.yml file for PostgreSQL.",
)
def dev(
    host: str,
    port: int,
    app: str,
    config_file: Path | None,
    env_file: Path | None,
    no_db_check: bool,
    compose_file: Path | None,
):
    """Run the development server with hot reload.

    Starts uvicorn with --reload flag for development.
    The server will automatically restart when code changes are detected.

    Aegra auto-discovers aegra.json by walking up the directory tree, so you
    can run 'aegra dev' from any subdirectory of your project.

    By default, Aegra will check if Docker is running and start PostgreSQL
    automatically if needed. Use --no-db-check to skip this behavior.

    Examples:

        aegra dev                        # Auto-discover config, start server

        aegra dev -c /path/to/aegra.json # Use specific config file

        aegra dev -e /path/to/.env       # Use specific .env file

        aegra dev --no-db-check          # Start without database check
    """
    import os

    # Discover or validate config file
    if config_file is not None:
        # User specified a config file explicitly
        resolved_config = config_file.resolve()
    else:
        # Auto-discover config file by walking up directory tree
        resolved_config = find_config_file()

    if resolved_config is None:
        console.print(
            "[bold red]Error:[/bold red] Could not find aegra.json or langgraph.json.\n"
            "Run [cyan]aegra init[/cyan] to create a new project, or specify "
            "[cyan]--config[/cyan] to point to your config file."
        )
        sys.exit(1)

    console.print(f"[dim]Using config: {resolved_config}[/dim]")

    # Set AEGRA_CONFIG env var so aegra-api resolves paths relative to config location
    os.environ["AEGRA_CONFIG"] = str(resolved_config)

    # Load environment variables from .env file
    # Default: look in config file's directory first, then cwd
    if env_file is None:
        # Try config directory first
        config_dir_env = resolved_config.parent / ".env"
        if config_dir_env.exists():
            env_file = config_dir_env

    loaded_env = load_env_file(env_file)
    if loaded_env:
        console.print(f"[dim]Loaded environment from: {loaded_env}[/dim]")
    elif env_file is not None:
        # User specified a file but it doesn't exist (shouldn't happen due to click validation)
        console.print(f"[yellow]Warning: .env file not found: {env_file}[/yellow]")

    # Check and start PostgreSQL unless disabled
    if not no_db_check:
        console.print()
        if not ensure_postgres_running(compose_file):
            console.print(
                "\n[bold red]Cannot start server without PostgreSQL.[/bold red]\n"
                "[dim]Use --no-db-check to skip this check.[/dim]"
            )
            sys.exit(1)
        console.print()

    # Build info panel content
    info_lines = [
        "[bold green]Starting Aegra development server[/bold green]\n",
        f"[cyan]Host:[/cyan] {host}",
        f"[cyan]Port:[/cyan] {port}",
        f"[cyan]App:[/cyan] {app}",
        f"[cyan]Config:[/cyan] {resolved_config}",
    ]
    if loaded_env:
        info_lines.append(f"[cyan]Env:[/cyan] {loaded_env}")
    info_lines.append("\n[dim]Press Ctrl+C to stop the server[/dim]")

    console.print(
        Panel(
            "\n".join(info_lines),
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

    process = None
    try:
        # Use Popen for better signal handling across platforms
        process = subprocess.Popen(cmd)

        # Set up signal handler to forward signals to child process
        def signal_handler(signum, frame):
            if process and process.poll() is None:  # Process still running
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            console.print("\n[yellow]Server stopped by user.[/yellow]")
            sys.exit(0)

        # Register signal handlers (SIGTERM not available on Windows)
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, signal_handler)

        # Wait for the process to complete
        returncode = process.wait()
        sys.exit(returncode)

    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] uvicorn is not installed.\n"
            "Install it with: [cyan]pip install uvicorn[/cyan]"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        # Fallback handler if signal handler didn't catch it
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
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
