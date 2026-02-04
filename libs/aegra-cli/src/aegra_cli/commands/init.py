"""Initialize a new Aegra project."""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()

AEGRA_CONFIG_TEMPLATE = {"graphs": {"agent": "./graphs/example/graph.py:graph"}}

ENV_EXAMPLE_TEMPLATE = """\
# PostgreSQL Configuration
POSTGRES_USER=aegra
POSTGRES_PASSWORD=aegra_secret
POSTGRES_HOST=localhost
POSTGRES_DB=aegra

# Authentication Type
# Options: noop, api_key, jwt
AUTH_TYPE=noop
"""

EXAMPLE_GRAPH_TEMPLATE = '''\
"""Example Aegra graph."""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    """Graph state."""
    messages: list[str]


def greeting_node(state: State) -> State:
    """A simple greeting node."""
    messages = state.get("messages", [])
    messages.append("Hello from Aegra!")
    return {"messages": messages}


# Build the graph
builder = StateGraph(State)
builder.add_node("greeting", greeting_node)
builder.add_edge(START, "greeting")
builder.add_edge("greeting", END)

# Compile the graph
graph = builder.compile()
'''

DOCKER_COMPOSE_TEMPLATE = """\
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-aegra}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aegra_secret}
      POSTGRES_DB: ${POSTGRES_DB:-aegra}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-aegra}"]
      interval: 5s
      timeout: 5s
      retries: 5

  aegra:
    build: .
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-aegra}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-aegra_secret}
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${POSTGRES_DB:-aegra}
      - AUTH_TYPE=${AUTH_TYPE:-noop}
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./graphs:/app/graphs:ro
      - ./aegra.json:/app/aegra.json:ro

volumes:
  postgres_data:
"""


def write_file(path: Path, content: str, force: bool) -> bool:
    """Write content to a file, respecting the force flag.

    Args:
        path: Path to write to
        content: Content to write
        force: Whether to overwrite existing files

    Returns:
        True if file was written, False if skipped
    """
    if path.exists() and not force:
        console.print(f"  [yellow]SKIP[/yellow] {path} (already exists)")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    console.print(f"  [green]CREATE[/green] {path}")
    return True


@click.command()
@click.option("--docker", is_flag=True, help="Include docker-compose.yml")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--path", type=click.Path(), default=".", help="Project directory")
def init(docker: bool, force: bool, path: str):
    """Initialize a new Aegra project.

    Creates the necessary configuration files and directory structure
    for a new Aegra project, including:

    \b
    - aegra.json: Graph configuration
    - .env.example: Environment variable template
    - graphs/example/graph.py: Example graph implementation
    - docker-compose.yml: Docker configuration (with --docker flag)
    """
    project_path = Path(path).resolve()

    console.print(
        Panel.fit(
            f"[bold blue]Initializing Aegra project[/bold blue]\n[dim]{project_path}[/dim]",
            border_style="blue",
        )
    )
    console.print()

    files_created = 0
    files_skipped = 0

    # Create aegra.json
    aegra_config_path = project_path / "aegra.json"
    aegra_config_content = json.dumps(AEGRA_CONFIG_TEMPLATE, indent=2) + "\n"
    if write_file(aegra_config_path, aegra_config_content, force):
        files_created += 1
    else:
        files_skipped += 1

    # Create .env.example
    env_example_path = project_path / ".env.example"
    if write_file(env_example_path, ENV_EXAMPLE_TEMPLATE, force):
        files_created += 1
    else:
        files_skipped += 1

    # Create example graph
    example_graph_path = project_path / "graphs" / "example" / "graph.py"
    if write_file(example_graph_path, EXAMPLE_GRAPH_TEMPLATE, force):
        files_created += 1
    else:
        files_skipped += 1

    # Create __init__.py files for the graphs package
    graphs_init_path = project_path / "graphs" / "__init__.py"
    if write_file(graphs_init_path, '"""Aegra graphs package."""\n', force):
        files_created += 1
    else:
        files_skipped += 1

    example_init_path = project_path / "graphs" / "example" / "__init__.py"
    if write_file(example_init_path, '"""Example graph package."""\n', force):
        files_created += 1
    else:
        files_skipped += 1

    # Create docker-compose.yml if requested
    if docker:
        docker_compose_path = project_path / "docker-compose.yml"
        if write_file(docker_compose_path, DOCKER_COMPOSE_TEMPLATE, force):
            files_created += 1
        else:
            files_skipped += 1

    # Print summary
    console.print()
    console.print(
        Panel.fit(
            f"[bold green]Project initialized![/bold green]\n\n"
            f"[green]{files_created}[/green] files created"
            + (f", [yellow]{files_skipped}[/yellow] files skipped" if files_skipped else ""),
            border_style="green",
        )
    )

    # Print next steps
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Copy [cyan].env.example[/cyan] to [cyan].env[/cyan] and configure")
    console.print("  2. Edit [cyan]aegra.json[/cyan] to add your graphs")
    console.print("  3. Run [cyan]aegra serve[/cyan] to start the server")

    if docker:
        console.print()
        console.print("[bold]Docker:[/bold]")
        console.print("  Run [cyan]docker-compose up[/cyan] to start all services")
