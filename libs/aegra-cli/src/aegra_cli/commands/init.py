"""Initialize a new Aegra project."""

import json
import re
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def slugify(name: str) -> str:
    """Convert a name to a valid Python/Docker identifier.

    Examples:
        "My Project" -> "my_project"
        "my-app" -> "my_app"
        "MyApp 2.0" -> "myapp_2_0"
    """
    # Convert to lowercase and replace spaces/hyphens with underscores
    slug = name.lower().replace(" ", "_").replace("-", "_")
    # Remove any characters that aren't alphanumeric or underscore
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    # Remove leading/trailing underscores and collapse multiple underscores
    slug = re.sub(r"_+", "_", slug).strip("_")
    # Ensure it doesn't start with a number
    if slug and slug[0].isdigit():
        slug = "project_" + slug
    return slug or "aegra_project"


def get_aegra_config(project_name: str, slug: str) -> dict:
    """Generate aegra.json config content."""
    return {
        "name": project_name,
        "graphs": {slug: f"./graphs/{slug}/graph.py:graph"},
    }


def get_env_example(slug: str) -> str:
    """Generate .env.example content."""
    return f"""\
# PostgreSQL Configuration
POSTGRES_USER={slug}
POSTGRES_PASSWORD={slug}_secret
POSTGRES_HOST=localhost
POSTGRES_DB={slug}

# Authentication Type
# Options: noop, api_key, jwt
AUTH_TYPE=noop
"""


def get_example_graph(project_name: str) -> str:
    """Generate example graph content."""
    return f'''\
"""{project_name} - Example graph."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    """Graph state."""

    messages: list[str]


def greeting_node(state: State) -> State:
    """A simple greeting node."""
    messages = state.get("messages", [])
    messages.append("Hello from {project_name}!")
    return {{"messages": messages}}


# Build the graph
builder = StateGraph(State)
builder.add_node("greeting", greeting_node)
builder.add_edge(START, "greeting")
builder.add_edge("greeting", END)

# Compile the graph
graph = builder.compile()
'''


def get_docker_compose(slug: str) -> str:
    """Generate docker-compose.yml content."""
    return f"""\
version: "3.8"

services:
  postgres:
    image: postgres:18
    container_name: {slug}-postgres
    environment:
      POSTGRES_USER: ${{POSTGRES_USER:-{slug}}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-{slug}_secret}}
      POSTGRES_DB: ${{POSTGRES_DB:-{slug}}}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${{POSTGRES_USER:-{slug}}}"]
      interval: 5s
      timeout: 5s
      retries: 5

  {slug}:
    build: .
    container_name: {slug}-api
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_USER=${{POSTGRES_USER:-{slug}}}
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD:-{slug}_secret}}
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${{POSTGRES_DB:-{slug}}}
      - AUTH_TYPE=${{AUTH_TYPE:-noop}}
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
@click.option(
    "--name",
    "-n",
    default=None,
    help="Project name (defaults to directory name).",
)
@click.option("--docker", is_flag=True, help="Include docker-compose.yml")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--path", type=click.Path(), default=".", help="Project directory")
def init(name: str | None, docker: bool, force: bool, path: str):
    """Initialize a new Aegra project.

    Creates the necessary configuration files and directory structure
    for a new Aegra project, including:

    \b
    - aegra.json: Graph configuration with project name
    - .env.example: Environment variable template
    - graphs/<name>/graph.py: Example graph implementation
    - docker-compose.yml: Docker configuration (with --docker flag)

    Examples:

        aegra init                          # Use directory name as project name

        aegra init --name "My AI Agent"     # Specify project name

        aegra init -n myproject --docker    # With Docker support
    """
    project_path = Path(path).resolve()

    # Determine project name - use provided name, or directory name
    if name is None:
        name = project_path.name
    slug = slugify(name)

    console.print(
        Panel.fit(
            f"[bold blue]Initializing Aegra project[/bold blue]\n\n"
            f"[cyan]Name:[/cyan] {name}\n"
            f"[cyan]Path:[/cyan] {project_path}",
            border_style="blue",
        )
    )
    console.print()

    files_created = 0
    files_skipped = 0

    # Create aegra.json
    aegra_config_path = project_path / "aegra.json"
    aegra_config_content = json.dumps(get_aegra_config(name, slug), indent=2) + "\n"
    if write_file(aegra_config_path, aegra_config_content, force):
        files_created += 1
    else:
        files_skipped += 1

    # Create .env.example
    env_example_path = project_path / ".env.example"
    if write_file(env_example_path, get_env_example(slug), force):
        files_created += 1
    else:
        files_skipped += 1

    # Create example graph (using slugified name for directory)
    example_graph_path = project_path / "graphs" / slug / "graph.py"
    if write_file(example_graph_path, get_example_graph(name), force):
        files_created += 1
    else:
        files_skipped += 1

    # Create __init__.py files for the graphs package
    graphs_init_path = project_path / "graphs" / "__init__.py"
    if write_file(graphs_init_path, f'"""{name} graphs package."""\n', force):
        files_created += 1
    else:
        files_skipped += 1

    example_init_path = project_path / "graphs" / slug / "__init__.py"
    if write_file(example_init_path, f'"""{name} graph."""\n', force):
        files_created += 1
    else:
        files_skipped += 1

    # Create docker-compose.yml if requested
    if docker:
        docker_compose_path = project_path / "docker-compose.yml"
        if write_file(docker_compose_path, get_docker_compose(slug), force):
            files_created += 1
        else:
            files_skipped += 1

    # Print summary
    console.print()
    console.print(
        Panel.fit(
            f"[bold green]Project '{name}' initialized![/bold green]\n\n"
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
    console.print("  3. Run [cyan]aegra dev[/cyan] to start the server")

    if docker:
        console.print()
        console.print("[bold]Docker:[/bold]")
        console.print("  Run [cyan]aegra up[/cyan] to start all services")
