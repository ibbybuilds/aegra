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
from aegra_cli.commands.init import (
    get_docker_compose_dev,
    get_docker_compose_prod,
    get_dockerfile,
    slugify,
)
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


def get_project_slug(config_path: Path | None) -> str:
    """Get project slug from config file or directory name.

    Args:
        config_path: Path to aegra.json config file

    Returns:
        Slugified project name
    """
    import json

    if config_path and config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
                if "name" in config:
                    return slugify(config["name"])
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback to directory name
    return slugify(Path.cwd().name)


def ensure_docker_compose_dev(project_path: Path, slug: str) -> Path:
    """Ensure docker-compose.yml exists for development.

    Args:
        project_path: Project directory path
        slug: Project slug for naming

    Returns:
        Path to docker-compose.yml
    """
    compose_path = project_path / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[cyan]Creating[/cyan] {compose_path}")
        compose_path.write_text(get_docker_compose_dev(slug))
    return compose_path


def ensure_docker_files_prod(project_path: Path, slug: str) -> Path:
    """Ensure production Docker files exist.

    Args:
        project_path: Project directory path
        slug: Project slug for naming

    Returns:
        Path to docker-compose.prod.yml
    """
    # Create docker-compose.prod.yml if needed
    compose_path = project_path / "docker-compose.prod.yml"
    if not compose_path.exists():
        console.print(f"[cyan]Creating[/cyan] {compose_path}")
        compose_path.write_text(get_docker_compose_prod(slug))

    # Create Dockerfile if needed
    dockerfile_path = project_path / "Dockerfile"
    if not dockerfile_path.exists():
        console.print(f"[cyan]Creating[/cyan] {dockerfile_path}")
        dockerfile_path.write_text(get_dockerfile())

    return compose_path


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

        # Auto-generate docker-compose.yml if not specified and doesn't exist
        if compose_file is None:
            project_path = resolved_config.parent
            default_compose = project_path / "docker-compose.yml"
            if not default_compose.exists():
                slug = get_project_slug(resolved_config)
                compose_file = ensure_docker_compose_dev(project_path, slug)

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
    "--host",
    default="0.0.0.0",  # noqa: S104  # nosec B104 - intentional for Docker
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
    "--workers",
    "-w",
    default=1,
    type=int,
    help="Number of worker processes.",
    show_default=True,
)
def serve(host: str, port: int, app: str, config_file: Path | None, workers: int):
    """Run the production server.

    Starts uvicorn without --reload for production use.
    This command is typically used inside Docker containers.

    Examples:

        aegra serve                         # Start production server

        aegra serve --host 0.0.0.0 --port 8080

        aegra serve -w 4                    # Use 4 workers
    """
    import os

    # Discover or validate config file
    if config_file is not None:
        resolved_config = config_file.resolve()
    else:
        resolved_config = find_config_file()

    if resolved_config is None:
        console.print(
            "[bold red]Error:[/bold red] Could not find aegra.json or langgraph.json.\n"
            "Run [cyan]aegra init[/cyan] to create a new project, or specify "
            "[cyan]--config[/cyan] to point to your config file."
        )
        sys.exit(1)

    # Set AEGRA_CONFIG env var
    os.environ["AEGRA_CONFIG"] = str(resolved_config)

    console.print(
        Panel(
            f"[bold green]Starting Aegra production server[/bold green]\n\n"
            f"[cyan]Host:[/cyan] {host}\n"
            f"[cyan]Port:[/cyan] {port}\n"
            f"[cyan]Workers:[/cyan] {workers}\n"
            f"[cyan]Config:[/cyan] {resolved_config}",
            title="[bold]Aegra Server[/bold]",
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
    ]

    if workers > 1:
        cmd.extend(["--workers", str(workers)])

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
        console.print("\n[yellow]Server stopped.[/yellow]")
        sys.exit(0)


@cli.command()
@click.option(
    "--file",
    "-f",
    "compose_file",
    default=None,
    type=click.Path(path_type=Path),
    help="Path to docker-compose file (default: docker-compose.prod.yml).",
)
@click.option(
    "--build",
    is_flag=True,
    default=True,
    help="Build images before starting containers (default: true).",
)
@click.option(
    "--no-build",
    is_flag=True,
    default=False,
    help="Skip building images.",
)
@click.option(
    "--dev",
    "use_dev",
    is_flag=True,
    default=False,
    help="Use development compose (docker-compose.yml with postgres only).",
)
@click.argument("services", nargs=-1)
def up(
    compose_file: Path | None, build: bool, no_build: bool, use_dev: bool, services: tuple[str, ...]
):
    """Start services with Docker Compose.

    By default, uses docker-compose.prod.yml which builds and runs the full stack.
    Use --dev to only start postgres (same as aegra dev without the local server).

    Auto-generates Docker files if they don't exist:
    - docker-compose.prod.yml (production stack)
    - Dockerfile (for building the app image)

    Examples:

        aegra up                    # Build and start all services (production)

        aegra up --dev              # Start only postgres (development)

        aegra up --no-build         # Start without rebuilding

        aegra up -f ./custom.yml    # Use custom compose file
    """
    # Determine which compose file to use
    project_path = Path.cwd()
    config_file = find_config_file()
    slug = get_project_slug(config_file)

    if compose_file is None:
        if use_dev:
            compose_file = ensure_docker_compose_dev(project_path, slug)
        else:
            compose_file = ensure_docker_files_prod(project_path, slug)
    elif not compose_file.exists():
        console.print(f"[bold red]Error:[/bold red] Compose file not found: {compose_file}")
        sys.exit(1)

    mode = "development" if use_dev else "production"
    console.print(
        Panel(
            f"[bold green]Starting Aegra services ({mode})[/bold green]\n\n"
            f"[cyan]Compose file:[/cyan] {compose_file}",
            title="[bold]Aegra Up[/bold]",
            border_style="green",
        )
    )

    cmd = ["docker", "compose", "-f", str(compose_file)]

    cmd.append("up")
    cmd.append("-d")

    # Build unless --no-build is specified (and not in dev mode)
    if not no_build and not use_dev:
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
            console.print()
            console.print(
                "[dim]View logs:    docker compose -f " + str(compose_file) + " logs -f[/dim]"
            )
            console.print("[dim]Stop:         aegra down[/dim]")
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
    type=click.Path(path_type=Path),
    help="Path to docker-compose file.",
)
@click.option(
    "--volumes",
    "-v",
    is_flag=True,
    default=False,
    help="Remove named volumes declared in the compose file.",
)
@click.option(
    "--all",
    "stop_all",
    is_flag=True,
    default=False,
    help="Stop services from both dev and prod compose files.",
)
@click.argument("services", nargs=-1)
def down(compose_file: Path | None, volumes: bool, stop_all: bool, services: tuple[str, ...]):
    """Stop services with Docker Compose.

    Runs 'docker compose down' to stop and remove containers.
    By default, stops services from docker-compose.prod.yml if it exists,
    otherwise from docker-compose.yml.

    Use --all to stop services from both compose files.

    Examples:

        aegra down                  # Stop services

        aegra down --all            # Stop all dev and prod services

        aegra down -v               # Stop and remove volumes

        aegra down -f ./custom.yml  # Stop specific compose file
    """
    console.print(
        Panel(
            "[bold yellow]Stopping Aegra services[/bold yellow]",
            title="[bold]Aegra Down[/bold]",
            border_style="yellow",
        )
    )

    if volumes:
        console.print("[yellow]Warning:[/yellow] Removing volumes - data will be lost!")

    project_path = Path.cwd()
    compose_files_to_stop: list[Path] = []

    if compose_file:
        if compose_file.exists():
            compose_files_to_stop.append(compose_file)
        else:
            console.print(f"[bold red]Error:[/bold red] Compose file not found: {compose_file}")
            sys.exit(1)
    elif stop_all:
        # Stop both dev and prod
        dev_compose = project_path / "docker-compose.yml"
        prod_compose = project_path / "docker-compose.prod.yml"
        if prod_compose.exists():
            compose_files_to_stop.append(prod_compose)
        if dev_compose.exists():
            compose_files_to_stop.append(dev_compose)
    else:
        # Default: try prod first, then dev
        prod_compose = project_path / "docker-compose.prod.yml"
        dev_compose = project_path / "docker-compose.yml"
        if prod_compose.exists():
            compose_files_to_stop.append(prod_compose)
        elif dev_compose.exists():
            compose_files_to_stop.append(dev_compose)

    if not compose_files_to_stop:
        console.print("[yellow]No docker-compose files found. Nothing to stop.[/yellow]")
        sys.exit(0)

    overall_success = True
    for cf in compose_files_to_stop:
        console.print(f"\n[cyan]Stopping:[/cyan] {cf}")

        cmd = ["docker", "compose", "-f", str(cf), "down"]

        if volumes:
            cmd.append("-v")

        if services:
            cmd.extend(services)

        console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

        try:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                overall_success = False
        except FileNotFoundError:
            console.print(
                "[bold red]Error:[/bold red] docker is not installed or not in PATH.\n"
                "Please install Docker Desktop or Docker Engine."
            )
            sys.exit(1)

    if overall_success:
        console.print("\n[bold green]Services stopped successfully![/bold green]")
        sys.exit(0)
    else:
        console.print("\n[bold red]Some services failed to stop.[/bold red]")
        sys.exit(1)


# Register command groups and commands from the commands package
cli.add_command(db)
cli.add_command(init)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
