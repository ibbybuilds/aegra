# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project: Aegra — Open Source LangGraph Backend (Agent Protocol Server)

## Development Commands

### Environment Setup

```bash
# Install dependencies
uv sync

# Activate virtual environment (IMPORTANT for migrations)
source .venv/bin/activate

# Start database
docker compose up postgres -d

# Apply migrations
python3 scripts/migrate.py upgrade
```

### Running the Application

**Option 1: Docker (Recommended for beginners)**

```bash
# Start everything (database + migrations + server)
docker compose up aegra
```

**Option 2: Local Development (Recommended for advanced users)**

```bash
# Start development server with auto-reload
uv run uvicorn src.agent_server.main:app --reload

# Start with specific host/port
uv run uvicorn src.agent_server.main:app --host 0.0.0.0 --port 8000 --reload

# Start development database
docker compose up postgres -d
```

### Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api/test_assistants.py

# Run tests with async support
uv run pytest -v --asyncio-mode=auto

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Health check endpoint test
curl http://localhost:8000/health
```

### Database Management

```bash
# Database migrations (using our custom script)
python3 scripts/migrate.py upgrade
python3 scripts/migrate.py revision -m "description"
python3 scripts/migrate.py revision --autogenerate -m "description"

# Check migration status
python3 scripts/migrate.py current
python3 scripts/migrate.py history

# Reset database (development)
python3 scripts/migrate.py reset

# Start database
docker compose up postgres -d
```

### Code Quality (Optional - not currently configured)

```bash
# If ruff is added to dependencies, use:
# uv run ruff check .
# uv run ruff format .

# If mypy is added, use:
# uv run mypy src --cache-dir .mypy_cache
```

## High-Level Architecture

Aegra is an **Agent Protocol server** that acts as an HTTP wrapper around **official LangGraph packages**. The key architectural principle is that LangGraph handles ALL state persistence and graph execution, while the FastAPI layer only provides Agent Protocol compliance.

### Core Integration Pattern

**Database Architecture**: The system uses a hybrid approach:

- **LangGraph manages state**: Official `AsyncPostgresSaver` and `AsyncPostgresStore` handle conversation checkpoints, state history, and long-term memory
- **Minimal metadata tables**: Our SQLAlchemy models only track Agent Protocol metadata (assistants, runs, thread_metadata)
- **URL format difference**: LangGraph requires `postgresql://` while our SQLAlchemy uses `postgresql+asyncpg://`

### Configuration System

**aegra.json**: Central configuration file that defines:

- Graph definitions: `"weather_agent": "./graphs/weather_agent.py:graph"`
- Authentication: `"auth": {"path": "./auth.py:auth"}`
- Dependencies and environment

**auth.py**: Uses LangGraph SDK Auth patterns:

- `@auth.authenticate` decorator for user authentication
- `@auth.on.{resource}.{action}` for resource-level authorization
- Returns `Auth.types.MinimalUserDict` with user identity and metadata

### Database Manager Pattern

**DatabaseManager** (src/agent_server/core/database.py):

- Initializes both SQLAlchemy engine and LangGraph components
- Handles URL conversion between asyncpg and psycopg formats
- Provides singleton access to checkpointer and store instances
- Auto-creates LangGraph tables via `.setup()` calls
- **Note**: Database schema is now managed by Alembic migrations (see `alembic/versions/`)

### Graph Loading Strategy

Agents are Python modules that export a compiled `graph` variable:

```python
# graphs/weather_agent.py
workflow = StateGraph(WeatherState)
# ... define nodes and edges
graph = workflow.compile()  # Must export as 'graph'
```

### FastAPI Integration

**Lifespan Management**: The app uses `@asynccontextmanager` to properly initialize/cleanup LangGraph components during FastAPI startup/shutdown.

**Health Checks**: Comprehensive health endpoint tests connectivity to:

- SQLAlchemy database engine
- LangGraph checkpointer
- LangGraph store

### Authentication Flow

1. HTTP request with Authorization header
2. LangGraph SDK Auth extracts and validates token
3. Returns user context with identity, permissions, org_id
4. Resource handlers filter data based on user context
5. Multi-tenant isolation via user metadata injection

## Key Dependencies

- **langgraph**: Core graph execution framework
- **langgraph-checkpoint-postgres**: Official PostgreSQL state persistence
- **langgraph-sdk**: Authentication and SDK components
- **psycopg[binary]**: Required by LangGraph packages (not asyncpg)
- **FastAPI + uvicorn**: HTTP API layer
- **SQLAlchemy**: For Agent Protocol metadata tables only
- **alembic**: Database migration management
- **asyncpg**: Async PostgreSQL driver for SQLAlchemy
- **greenlet**: Required for async SQLAlchemy operations

## Authentication System

The server uses environment-based authentication switching with proper LangGraph SDK integration:

**Authentication Types:**

- `AUTH_TYPE=noop` - No authentication (allow all requests, useful for development)
- `AUTH_TYPE=custom` - Custom authentication (integrate with your auth service)

**Configuration:**

```bash
# Set in .env file
AUTH_TYPE=noop  # or "custom"
```

**Custom Authentication:**
To implement custom auth, modify the `@auth.authenticate` and `@auth.on` decorated functions in `auth.py`:

1. Update the custom `authenticate()` function to integrate with your auth service (Firebase, JWT, etc.)
2. The `authorize()` function handles user-scoped access control automatically
3. Add any additional environment variables needed for your auth service

**Middleware Integration:**
Authentication runs as middleware on every request. LangGraph operations automatically inherit the authenticated user context for proper data scoping.

## Development Patterns

**Import patterns**: Always use relative imports within the package and absolute imports for external dependencies.

**Database access**: Use `db_manager.get_checkpointer()` and `db_manager.get_store()` for LangGraph operations, `db_manager.get_engine()` for metadata queries.

**Authentication**: Use `get_current_user(request)` dependency to access authenticated user in FastAPI routes. The user is automatically set by LangGraph auth middleware.

**Error handling**: Use `Auth.exceptions.HTTPException` for authentication errors to maintain LangGraph SDK compatibility.

**Testing**: Tests should be async-aware and use pytest-asyncio for proper async test support.

Always run test commands (`uv run pytest`) before completing tasks. Linting and type checking tools are not currently configured for this project.

## Migration System

The project now uses Alembic for database schema management:

**Key Files:**

- `alembic.ini`: Alembic configuration
- `alembic/env.py`: Environment setup with async support
- `alembic/versions/`: Migration files
- `scripts/migrate.py`: Custom migration management script

**Migration Commands:**

```bash
# Apply migrations
python3 scripts/migrate.py upgrade

# Create new migration
python3 scripts/migrate.py revision -m "description"

# Check status
python3 scripts/migrate.py current
python3 scripts/migrate.py history

# Reset (destructive)
python3 scripts/migrate.py reset
```

**Important Notes:**

- Always activate virtual environment before running migrations
- Docker automatically runs migrations on startup
- Migration files are version-controlled and should be committed with code changes
