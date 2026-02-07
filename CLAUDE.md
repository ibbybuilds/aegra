# AGENTS.md

This file provides context for AI coding agents working with this repository.

## Project Overview

**Aegra** is an open-source, self-hosted alternative to LangGraph Platform. It's a production-ready Agent Protocol server that allows you to run AI agents on your own infrastructure without vendor lock-in.

**Key characteristics:**
- Drop-in replacement for LangGraph Platform using the same LangGraph SDK
- Self-hosted on your own PostgreSQL database
- Agent Protocol compliant (works with Agent Chat UI, LangGraph Studio, CopilotKit)
- Python 3.11+ with FastAPI and PostgreSQL

## Quick Start Commands

### Using the CLI (Recommended)

```bash
# Install the CLI
pip install aegra-cli

# Initialize a new project
aegra init --docker

# Start PostgreSQL with Docker
aegra up postgres

# Apply database migrations
aegra db upgrade

# Run development server with hot reload
aegra dev

# Or start all services with Docker
aegra up
```

### Manual Setup

```bash
# Install dependencies
cd libs/aegra-api && uv sync

# Start database
docker compose up postgres -d

# Apply migrations
cd libs/aegra-api && alembic upgrade head

# Run development server
cd libs/aegra-api && uv run uvicorn aegra_api.main:app --reload

# Or run everything with Docker
docker compose up aegra
```

## Testing

```bash
# Run all tests
cd libs/aegra-api && uv run pytest

# Run specific test file
cd libs/aegra-api && uv run pytest tests/unit/test_api/test_assistants.py

# Run with coverage
cd libs/aegra-api && uv run pytest --cov=src --cov-report=html

# Run e2e tests (requires running server)
cd libs/aegra-api && uv run pytest tests/e2e/

# Health check
curl http://localhost:8000/health
```

**Important:** Always run `uv run pytest` before completing tasks to verify changes don't break existing functionality.

## Code Quality

```bash
# Linting
cd libs/aegra-api && uv run ruff check .
cd libs/aegra-api && uv run ruff format .

# Type checking
cd libs/aegra-api && uv run mypy src

# Security scanning
cd libs/aegra-api && uv run bandit -r src
```

## Database Migrations

### Using the CLI (Recommended)

```bash
# Apply all pending migrations
aegra db upgrade

# Check current migration version
aegra db current

# Show migration history
aegra db history
aegra db history --verbose

# Downgrade by one revision
aegra db downgrade

# Downgrade to specific revision
aegra db downgrade abc123
```

### Using Alembic Directly

```bash
# Apply migrations
cd libs/aegra-api && alembic upgrade head

# Create new migration
cd libs/aegra-api && alembic revision -m "description"

# Auto-generate migration from model changes
cd libs/aegra-api && alembic revision --autogenerate -m "description"

# Check status
cd libs/aegra-api && alembic current
cd libs/aegra-api && alembic history
```

## Project Structure

```
aegra/
├── libs/
│   ├── aegra-api/                    # Core API package
│   │   ├── src/aegra_api/            # Main application code
│   │   │   ├── api/                  # Agent Protocol endpoints
│   │   │   │   ├── assistants.py     # /assistants CRUD
│   │   │   │   ├── threads.py        # /threads and state management
│   │   │   │   ├── runs.py           # /runs execution and streaming
│   │   │   │   └── store.py          # /store vector storage
│   │   │   ├── services/             # Business logic layer
│   │   │   ├── core/                 # Infrastructure (database, auth, orm)
│   │   │   ├── models/               # Pydantic request/response schemas
│   │   │   ├── middleware/           # ASGI middleware
│   │   │   ├── observability/        # OpenTelemetry tracing
│   │   │   ├── utils/                # Helper functions
│   │   │   ├── main.py               # FastAPI app entry point
│   │   │   ├── config.py             # HTTP/store config loading
│   │   │   └── settings.py           # Environment settings
│   │   ├── tests/                    # Test suite
│   │   ├── alembic/                  # Database migrations
│   │   └── pyproject.toml
│   │
│   └── aegra-cli/                    # CLI package
│       └── src/aegra_cli/
│           ├── cli.py                # Main CLI entry point
│           └── commands/             # Command implementations
│               ├── db.py             # Database migration commands
│               └── init.py           # Project initialization
│
├── examples/                         # Example agents and configs
│   ├── react_agent/                  # Basic ReAct agent
│   ├── react_agent_hitl/             # ReAct with human-in-loop
│   ├── subgraph_agent/               # Hierarchical agents
│   ├── subgraph_hitl_agent/          # Hierarchical with HITL
│   ├── custom_routes_example.py      # Custom routes example
│   └── jwt_mock_auth_example.py      # JWT auth example
│
├── docs/                             # Documentation
├── deployments/                      # Docker configs
├── aegra.json                        # Agent graph definitions
└── docker-compose.yml                # Local development setup
```

## Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI HTTP Layer (Agent Protocol API)                │
│  └─ /assistants, /threads, /runs, /store endpoints     │
├─────────────────────────────────────────────────────────┤
│  Middleware Stack                                        │
│  └─ Auth, CORS, Structured Logging, Correlation ID     │
├─────────────────────────────────────────────────────────┤
│  Service Layer (Business Logic)                          │
│  └─ LangGraphService, AssistantService, StreamingService│
├─────────────────────────────────────────────────────────┤
│  LangGraph Runtime                                       │
│  └─ Graph execution, state management, tool execution   │
├─────────────────────────────────────────────────────────┤
│  Database Layer (PostgreSQL)                             │
│  └─ AsyncPostgresSaver (checkpoints), AsyncPostgresStore│
└─────────────────────────────────────────────────────────┘
```

**Key principle:** LangGraph handles ALL state persistence and graph execution. FastAPI provides only HTTP/Agent Protocol compliance.

### Database Architecture

The system uses a hybrid approach with two connection pools:

1. **SQLAlchemy Pool** (asyncpg driver) - Metadata tables: assistants, threads, runs
2. **LangGraph Pool** (psycopg driver) - State checkpoints, vector embeddings

**URL format difference:** LangGraph requires `postgresql://` while SQLAlchemy uses `postgresql+asyncpg://`

### Configuration Files

**aegra.json** - Central configuration:
```json
{
  "graphs": {
    "agent": "./examples/react_agent/graph.py:graph"
  },
  "http": {
    "app": "./examples/custom_routes_example.py:app"
  }
}
```

**jwt_mock_auth_example.py** - Example authentication using LangGraph SDK Auth patterns:
- `@auth.authenticate` decorator for user authentication
- `@auth.on.{resource}.{action}` for authorization handlers
- Returns `Auth.types.MinimalUserDict` with user identity

### Graph Loading

Agents are Python modules exporting a compiled `graph` variable:
```python
# examples/react_agent/graph.py
builder = StateGraph(State)
# ... define nodes and edges
graph = builder.compile()  # Must export as 'graph'
```

## Development Patterns

### Import Conventions
- Use absolute imports with `aegra_api.*` prefix
- Use proper Python typing everywhere (type hints for function parameters, return types, variables where helpful)

### Database Access
```python
# For LangGraph operations
checkpointer = db_manager.get_checkpointer()
store = db_manager.get_store()

# For metadata queries
engine = db_manager.get_engine()
```

### Authentication
```python
# Access authenticated user in routes
from aegra_api.core.auth_deps import get_current_user

@router.get("/example")
async def example(user: AuthenticatedUser = Depends(get_current_user)):
    # user.identity contains user ID
    # user.metadata contains additional info
    pass
```

### Error Handling
- Use `Auth.exceptions.HTTPException` for auth errors
- Use standard FastAPI `HTTPException` for other errors

### Testing
- Tests must be async-aware using pytest-asyncio
- Use fixtures from `tests/conftest.py`
- E2E tests require a running server instance

## Key Dependencies

| Package | Purpose |
|---------|---------|
| langgraph | Core graph execution framework |
| langgraph-checkpoint-postgres | Official PostgreSQL state persistence |
| langgraph-sdk | Authentication and SDK components |
| psycopg[binary] | Required by LangGraph (not asyncpg) |
| FastAPI + uvicorn | HTTP API layer |
| SQLAlchemy | Agent Protocol metadata tables only |
| alembic | Database migration management |
| asyncpg | Async PostgreSQL for SQLAlchemy |

## Authentication System

**Environment-based switching:**
- `AUTH_TYPE=noop` - No authentication (development)
- `AUTH_TYPE=custom` - Custom authentication (production)

**To implement custom auth:**
1. Modify `@auth.authenticate` in your auth file for your auth service
2. The `authorize()` function handles user-scoped access automatically
3. Add required environment variables for your auth service

## API Endpoints Overview

| Endpoint | Purpose |
|----------|---------|
| `POST /assistants` | Create assistant from graph_id |
| `GET /assistants` | List user's assistants |
| `POST /threads` | Create conversation thread |
| `GET /threads/{id}/state` | Get thread state |
| `POST /threads/{id}/runs` | Execute graph (streaming/background) |
| `POST /runs/{id}/stream` | Stream run events |
| `PUT /store` | Save to vector store |
| `POST /store/search` | Semantic search |

## Common Tasks

### Adding a New Graph
1. Create a new directory in `examples/`
2. Define your state schema and graph logic
3. Export compiled graph as `graph` variable
4. Add entry to `aegra.json` under `graphs`

### Adding a New API Endpoint
1. Create or modify router in `libs/aegra-api/src/aegra_api/api/`
2. Add Pydantic models in `libs/aegra-api/src/aegra_api/models/`
3. Implement business logic in `libs/aegra-api/src/aegra_api/services/`
4. Register router in `libs/aegra-api/src/aegra_api/main.py`

### Database Schema Changes
1. Modify SQLAlchemy models in `libs/aegra-api/src/aegra_api/core/orm.py`
2. Generate migration: `cd libs/aegra-api && alembic revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Apply: `cd libs/aegra-api && alembic upgrade head`

## Environment Variables

```bash
# Database
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_DB=aegra

# Auth
AUTH_TYPE=noop  # or "custom"

# Server
HOST=0.0.0.0
PORT=8000

# Config
AEGRA_CONFIG=aegra.json

# LLM (for example agents)
OPENAI_API_KEY=sk-...

# Observability (optional)
OTEL_TARGETS=LANGFUSE,PHOENIX
```

## PR Guidelines

- Run `cd libs/aegra-api && uv run pytest` before committing
- Run `cd libs/aegra-api && uv run ruff check .` for linting
- Include tests for new functionality
- Update migrations if modifying database schema
- Title format: `[component] Brief description`
