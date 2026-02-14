"""Template registry, renderers, and Docker file generators for Aegra projects."""

import json
import re
from importlib import resources
from string import Template

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES: list[dict[str, str]] = [
    {
        "id": "simple-chatbot",
        "name": "New Aegra Project",
        "description": "A simple chatbot with message memory.",
    },
    {
        "id": "react-agent",
        "name": "ReAct Agent",
        "description": "An agent with tools that reasons and acts step by step.",
    },
]


def get_template_choices() -> list[dict[str, str]]:
    """Return the list of available project templates.

    Returns:
        List of template dicts with id, name, and description.
    """
    return TEMPLATES


# ---------------------------------------------------------------------------
# Template loading / rendering
# ---------------------------------------------------------------------------

_TEMPLATES_PKG = "aegra_cli.templates"

_VALID_TEMPLATE_IDS = frozenset(t["id"] for t in TEMPLATES)


def _validate_template_id(template_id: str) -> None:
    """Raise ValueError if template_id is not a known template."""
    if template_id not in _VALID_TEMPLATE_IDS:
        raise ValueError(
            f"Unknown template '{template_id}'. "
            f"Valid templates: {', '.join(sorted(_VALID_TEMPLATE_IDS))}"
        )


def load_template_manifest(template_id: str) -> dict:
    """Read and return manifest.json for a template.

    Args:
        template_id: Template directory name (e.g. "simple-chatbot").

    Returns:
        Parsed manifest dict.

    Raises:
        ValueError: If template_id is not a known template.
    """
    _validate_template_id(template_id)
    text = (
        resources.files(_TEMPLATES_PKG)
        .joinpath(template_id, "manifest.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def render_template_file(template_id: str, filename: str, variables: dict[str, str]) -> str:
    """Load a template file and perform safe_substitute.

    Args:
        template_id: Template directory name.
        filename: File inside the template directory.
        variables: Substitution mapping ($slug, $project_name, ...).

    Returns:
        Rendered string.

    Raises:
        ValueError: If template_id is not a known template.
    """
    _validate_template_id(template_id)
    raw = (
        resources.files(_TEMPLATES_PKG).joinpath(template_id, filename).read_text(encoding="utf-8")
    )
    return Template(raw).safe_substitute(variables)


def render_shared_template_file(filename: str, variables: dict[str, str]) -> str:
    """Load a template file from shared/ and perform safe_substitute.

    Args:
        filename: File inside the shared/ directory (e.g. "state.py.template").
        variables: Substitution mapping ($slug, $project_name, ...).

    Returns:
        Rendered string.
    """
    raw = resources.files(_TEMPLATES_PKG).joinpath("shared", filename).read_text(encoding="utf-8")
    return Template(raw).safe_substitute(variables)


def load_shared_file(filename: str) -> str:
    """Load a file from the shared/ directory (no substitution).

    Args:
        filename: File inside shared/ (e.g. "gitignore").

    Returns:
        File contents as a string.
    """
    return resources.files(_TEMPLATES_PKG).joinpath("shared", filename).read_text(encoding="utf-8")


def render_env_example(variables: dict[str, str]) -> str:
    """Render .env.example from the bundled template.

    Args:
        variables: Substitution mapping (must include $slug).

    Returns:
        Rendered .env.example content.
    """
    raw = (
        resources.files(_TEMPLATES_PKG).joinpath("env.example.template").read_text(encoding="utf-8")
    )
    return Template(raw).safe_substitute(variables)


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Convert a name to a valid Python/Docker identifier.

    Examples:
        "My Project" -> "my_project"
        "my-app" -> "my_app"
        "MyApp 2.0" -> "myapp_20"
    """
    slug = name.lower().replace(" ", "_").replace("-", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if slug and slug[0].isdigit():
        slug = "project_" + slug
    return slug or "aegra_project"


# ---------------------------------------------------------------------------
# Docker file generators (f-string based — avoids ${ } conflicts with YAML)
# ---------------------------------------------------------------------------


def get_docker_compose(slug: str) -> str:
    """Generate docker-compose.yml with both postgres and API services.

    Args:
        slug: Project slug used for container/database naming.

    Returns:
        docker-compose.yml content string.
    """
    return f"""\
# Docker Compose - PostgreSQL + API
# aegra dev  -> docker compose up postgres -d  (database only)
# aegra up   -> docker compose up --build      (full stack)

services:
  postgres:
    image: pgvector/pgvector:pg18
    container_name: {slug}-postgres
    environment:
      POSTGRES_USER: ${{POSTGRES_USER:-{slug}}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-{slug}_secret}}
      POSTGRES_DB: ${{POSTGRES_DB:-{slug}}}
    ports:
      - "${{POSTGRES_PORT:-5432}}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${{POSTGRES_USER:-{slug}}}"]
      interval: 5s
      timeout: 5s
      retries: 5

  {slug}:
    build: .
    container_name: {slug}-api
    ports:
      - "${{PORT:-8000}}:8000"
    env_file:
      - .env
    environment:
      - POSTGRES_USER=${{POSTGRES_USER:-{slug}}}
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD:-{slug}_secret}}
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${{POSTGRES_DB:-{slug}}}
      - AEGRA_CONFIG=aegra.json
      - AUTH_TYPE=${{AUTH_TYPE:-noop}}
      - PORT=${{PORT:-8000}}
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      start_period: 10s
    volumes:
      - ./src:/app/src:ro
      - ./aegra.json:/app/aegra.json:ro

volumes:
  postgres_data:
"""


def get_dockerfile() -> str:
    """Generate Dockerfile for production builds.

    Returns:
        Dockerfile content string.
    """
    return """\
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Create non-root user for runtime
RUN addgroup --system app && adduser --system --ingroup app app

# -----------------------------
# Builder stage
# -----------------------------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY pyproject.toml ./
COPY uv.loc[k] ./
RUN uv sync --no-dev --no-install-project --compile-bytecode

# Copy source and install project
COPY src/ ./src/
RUN uv sync --no-dev --compile-bytecode

# -----------------------------
# Runtime stage
# -----------------------------
FROM base AS final

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates \\
    libpq5 \\
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY aegra.json .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER app

CMD ["aegra", "serve", "--host", "0.0.0.0", "--port", "8000"]
"""
