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

```bash
# Install dependencies
uv sync

# Activate virtual environment (required for migrations)
source .venv/bin/activate

# Start database
docker compose up postgres -d

# Apply migrations
python3 scripts/migrate.py upgrade

# Run development server
uv run uvicorn src.agent_server.main:app --reload

# Or run everything with Docker
docker compose up aegra
```

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_api/test_assistants.py

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run e2e tests (requires running server)
uv run pytest tests/e2e/

# Health check
curl http://localhost:8000/health
```

**Important:** Always run `uv run pytest` before completing tasks to verify changes don't break existing functionality.

## Code Quality

```bash
# Linting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src

# Security scanning
uv run bandit -r src
```

## Database Migrations

```bash
# Apply migrations
python3 scripts/migrate.py upgrade

# Create new migration
python3 scripts/migrate.py revision -m "description"

# Auto-generate migration from model changes
python3 scripts/migrate.py revision --autogenerate -m "description"

# Check status
python3 scripts/migrate.py current
python3 scripts/migrate.py history

# Reset database (destructive - development only)
python3 scripts/migrate.py reset
```

**Note:** Always activate the virtual environment before running migrations.

## Project Structure

```
aegra/
├── src/agent_server/              # Main application code
│   ├── api/                       # Agent Protocol endpoints
│   │   ├── assistants.py          # /assistants CRUD
│   │   ├── threads.py             # /threads and state management
│   │   ├── runs.py                # /runs execution and streaming
│   │   └── store.py               # /store vector storage
│   ├── services/                  # Business logic layer
│   │   ├── langgraph_service.py   # Graph loading and caching
│   │   ├── assistant_service.py   # Assistant business logic
│   │   ├── streaming_service.py   # SSE connection management
│   │   ├── graph_streaming.py     # Graph execution streaming
│   │   └── thread_state_service.py # State management
│   ├── core/                      # Infrastructure
│   │   ├── database.py            # DatabaseManager, pool setup
│   │   ├── auth_middleware.py     # LangGraph auth integration
│   │   ├── auth_deps.py           # FastAPI dependencies
│   │   ├── orm.py                 # SQLAlchemy models
│   │   └── health.py              # Health check endpoints
│   ├── models/                    # Pydantic request/response schemas
│   ├── middleware/                # ASGI middleware
│   ├── observability/             # Tracing and logging
│   ├── utils/                     # Helper functions
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # HTTP/store config loading
│   └── settings.py                # Environment settings
├── graphs/                        # Agent definitions (examples)
│   ├── react_agent/               # Basic ReAct agent
│   ├── react_agent_hitl/          # ReAct with human-in-loop
│   ├── subgraph_agent/            # Hierarchical agents
│   └── subgraph_hitl_agent/       # Hierarchical with HITL
├── alembic/                       # Database migrations
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   ├── e2e/                       # End-to-end tests
│   └── conftest.py                # Pytest configuration
├── auth.py                        # LangGraph auth configuration
├── aegra.json                     # Agent graph definitions
└── docker-compose.yml             # Local development setup
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
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "http": {
    "app": "./custom_routes_example.py:app"
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
# graphs/example/graph.py
builder = StateGraph(State)
# ... define nodes and edges
graph = builder.compile()  # Must export as 'graph'
```

## Development Patterns

### Import Conventions
- Use relative imports within the package
- Use absolute imports for external dependencies
- **Always use global/top-level imports** - Do NOT use inline/local imports inside functions
- Only use inline imports if circular dependency is **proven** (not assumed)
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
from agent_server.core.auth_deps import get_current_user

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
1. Modify `@auth.authenticate` in `auth.py` for your auth service
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
1. Create a new directory in `graphs/`
2. Define your state schema and graph logic
3. Export compiled graph as `graph` variable
4. Add entry to `aegra.json` under `graphs`

### Adding a New API Endpoint
1. Create or modify router in `src/agent_server/api/`
2. Add Pydantic models in `src/agent_server/models/`
3. Implement business logic in `src/agent_server/services/`
4. Register router in `src/agent_server/main.py`

### Database Schema Changes
1. Modify SQLAlchemy models in `src/agent_server/core/orm.py`
2. Generate migration: `python3 scripts/migrate.py revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Apply: `python3 scripts/migrate.py upgrade`

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
LANGFUSE_LOGGING=false
LANGFUSE_SECRET_KEY=...
```

## PR Guidelines

- Run `uv run pytest` before committing
- Run `uv run ruff check .` for linting
- Include tests for new functionality
- Update migrations if modifying database schema
- Title format: `[component] Brief description`
