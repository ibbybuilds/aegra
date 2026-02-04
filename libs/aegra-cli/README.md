# aegra-cli

Aegra CLI - Command-line interface for managing self-hosted agent deployments.

Aegra is an open-source, self-hosted alternative to LangGraph Platform. Use this CLI to initialize projects, run development servers, manage Docker services, and handle database migrations.

## Installation

### From PyPI

```bash
pip install aegra-cli
```

### From Source

```bash
# Clone the repository
git clone https://github.com/your-org/aegra.git
cd aegra/libs/aegra-cli

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

## Quick Start

```bash
# Initialize a new Aegra project
aegra init

# Start PostgreSQL with Docker
aegra up postgres

# Apply database migrations
aegra db upgrade

# Start the development server
aegra dev
```

## Commands

### `aegra version`

Show version information for aegra-cli and aegra-api.

```bash
aegra version
```

Output displays a table with versions for both packages.

---

### `aegra init`

Initialize a new Aegra project with configuration files and directory structure.

```bash
aegra init [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--docker` | Include docker-compose.yml in the generated files |
| `--force` | Overwrite existing files if they exist |
| `--path PATH` | Project directory (default: current directory) |

**Examples:**

```bash
# Initialize in current directory
aegra init

# Initialize with Docker Compose support
aegra init --docker

# Initialize in a specific directory, overwriting existing files
aegra init --path ./my-project --force
```

**Created Files:**

- `aegra.json` - Graph configuration
- `.env.example` - Environment variable template
- `graphs/example/graph.py` - Example graph implementation
- `graphs/__init__.py` - Package init file
- `graphs/example/__init__.py` - Example package init file
- `docker-compose.yml` - Docker configuration (only with `--docker` flag)

---

### `aegra dev`

Run the development server with hot reload.

```bash
aegra dev [OPTIONS]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--host HOST` | `127.0.0.1` | Host to bind the server to |
| `--port PORT` | `8000` | Port to bind the server to |
| `--app APP` | `aegra_api.main:app` | Application import path |

**Examples:**

```bash
# Start with defaults (localhost:8000)
aegra dev

# Start on all interfaces, port 3000
aegra dev --host 0.0.0.0 --port 3000

# Start with a custom app
aegra dev --app myapp.main:app
```

The server automatically restarts when code changes are detected.

---

### `aegra up`

Start services with Docker Compose.

```bash
aegra up [OPTIONS] [SERVICES...]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-f, --file FILE` | Path to docker-compose.yml file |
| `--build` | Build images before starting containers |

**Arguments:**

| Argument | Description |
|----------|-------------|
| `SERVICES` | Optional list of specific services to start |

**Examples:**

```bash
# Start all services
aegra up

# Start only postgres
aegra up postgres

# Build and start all services
aegra up --build

# Start with a custom compose file
aegra up -f ./docker-compose.prod.yml

# Start specific services with build
aegra up --build aegra postgres
```

---

### `aegra down`

Stop services with Docker Compose.

```bash
aegra down [OPTIONS] [SERVICES...]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-f, --file FILE` | Path to docker-compose.yml file |
| `-v, --volumes` | Remove named volumes declared in the compose file |

**Arguments:**

| Argument | Description |
|----------|-------------|
| `SERVICES` | Optional list of specific services to stop |

**Examples:**

```bash
# Stop all services
aegra down

# Stop only postgres
aegra down postgres

# Stop and remove volumes (WARNING: data will be lost)
aegra down -v

# Stop with a custom compose file
aegra down -f ./docker-compose.prod.yml
```

---

### `aegra db upgrade`

Apply all pending database migrations.

```bash
aegra db upgrade
```

Runs `alembic upgrade head` to apply all pending migrations and bring the database schema up to date.

**Example:**

```bash
aegra db upgrade
```

---

### `aegra db downgrade`

Downgrade database to a previous revision.

```bash
aegra db downgrade [REVISION]
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `REVISION` | `-1` | Target revision (use `-1` for one step back) |

**Examples:**

```bash
# Downgrade by one revision
aegra db downgrade

# Downgrade by two revisions
aegra db downgrade -2

# Downgrade to initial state (removes all migrations)
aegra db downgrade base

# Downgrade to a specific revision
aegra db downgrade abc123
```

---

### `aegra db current`

Show the current migration version.

```bash
aegra db current
```

Displays the current revision that the database is at. Useful for checking which migrations have been applied.

**Example:**

```bash
aegra db current
```

---

### `aegra db history`

Show migration history.

```bash
aegra db history [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed migration information |

**Examples:**

```bash
# Show migration history
aegra db history

# Show detailed history
aegra db history --verbose
aegra db history -v
```

---

## Environment Variables

The CLI respects the following environment variables (typically set via `.env` file):

```bash
# Database
POSTGRES_USER=aegra
POSTGRES_PASSWORD=aegra_secret
POSTGRES_HOST=localhost
POSTGRES_DB=aegra

# Authentication
AUTH_TYPE=noop  # Options: noop, api_key, jwt

# Server (for aegra dev)
HOST=0.0.0.0
PORT=8000

# Configuration
AEGRA_CONFIG=aegra.json
```

## Requirements

- Python 3.11+
- Docker (for `aegra up` and `aegra down` commands)
- PostgreSQL (or use Docker)

## Related Packages

- **aegra-api**: Core API package providing the Agent Protocol server
- **aegra**: Meta-package that installs both aegra-cli and aegra-api
