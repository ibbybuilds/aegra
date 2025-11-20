# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project: Aegra — Open Source LangGraph Backend (Agent Protocol Server)

## Development Commands

### Environment Setup

```bash
# Install dependencies
uv install

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

## Deployment Environments

Aegra supports two deployment environments with different strategies:

### Staging Environment (Railway)

**Platform**: Railway.app
**Branch**: `development`
**Deployment**: Automatic via Railway's GitHub integration
**Database**: Railway managed PostgreSQL (fully PostgreSQL-compatible)
**Configuration**: See `.env.staging.example` for required environment variables
**Documentation**: [Railway Deployment Guide](docs/RAILWAY_DEPLOYMENT.md)

**How it works:**
1. Push to `development` branch
2. GitHub Actions runs comprehensive CI checks (`.github/workflows/development-ci.yml`)
3. If CI passes, Railway automatically detects the push and deploys
4. Railway builds using `deployments/docker/Dockerfile`
5. Migrations run automatically, server starts
6. Health check on `/health` endpoint confirms deployment

**Setup**: Configure Railway project to watch the `development` branch. Railway will auto-deploy on every push. See `docs/RAILWAY_DEPLOYMENT.md` for detailed setup instructions.

### Production Environment (GKE)

**Platform**: Google Kubernetes Engine (GKE)
**Branch**: `main`
**Deployment**: Manual (images built automatically)
**Database**: GCP Cloud SQL for PostgreSQL (fully PostgreSQL-compatible)
**Configuration**: See `.env.production.example` for required environment variables
**Documentation**: [GKE Deployment Guide](docs/GKE_DEPLOYMENT.md)

**Current Status:**
- ✅ Production Dockerfile ready (`deployments/docker/Dockerfile.production`)
- ✅ GitHub Actions builds and pushes images to Google Container Registry
- ⏳ Kubernetes manifests coming soon (manual deployment required)

**How it works:**
1. Push to `main` branch or create git tag (e.g., `v1.0.0`)
2. GitHub Actions runs comprehensive CI checks + E2E tests (`.github/workflows/production.yml`)
3. Builds production Docker image using `Dockerfile.production`
4. Tags image with git SHA, timestamp, and `latest` (or semver if from tag)
5. Pushes to Google Container Registry / Artifact Registry
6. Manual: Update K8s deployment with new image tag

**Setup**: Configure GitHub secrets (`GCP_PROJECT_ID`, `GCP_SA_KEY`, `GCR_REGISTRY`). See `docs/GKE_DEPLOYMENT.md` for detailed setup instructions.

### Database Compatibility

Both Railway PostgreSQL and GCP Cloud SQL for PostgreSQL are **100% compatible** with Aegra's LangGraph integration:
- LangGraph's `AsyncPostgresSaver` (checkpoints) uses standard PostgreSQL protocol
- LangGraph's `AsyncPostgresStore` (long-term memory) uses standard PostgreSQL protocol
- No code changes needed between environments, only connection string updates

## CI/CD Workflows

Aegra uses GitHub Actions for continuous integration and deployment automation:

### 1. Feature Branch CI (`.github/workflows/ci.yml`)

**Triggers**: Pull requests to any branch except `development` or `main`
**Purpose**: Fast feedback for work-in-progress features
**Runs**:
- Code formatting check (Ruff)
- Linting (Ruff)
- Security scan (Bandit, non-blocking)
- Type checking (MyPy, non-blocking)
- Unit tests with coverage (excludes E2E tests)

**Duration**: ~2-3 minutes (fast feedback loop)

### 2. Development CI (`.github/workflows/development-ci.yml`)

**Triggers**: Pushes and pull requests to `development` branch
**Purpose**: Comprehensive validation before staging deployment
**Runs**:
- All checks from Feature Branch CI
- **E2E tests with PostgreSQL service** (includes full server startup)
- Database migrations test
- Health check validation

**Duration**: ~5-8 minutes (includes E2E tests)

**Note**: Railway automatically deploys after this workflow passes.

### 3. Production Build (`.github/workflows/production.yml`)

**Triggers**: Pushes to `main` branch or version tags (e.g., `v1.2.3`)
**Purpose**: Build and push production-ready Docker images
**Runs**:
- All checks from Development CI
- Builds production Docker image (`Dockerfile.production`)
- Authenticates to Google Cloud
- Tags with multiple identifiers:
  - `sha-{git-sha}` (e.g., `sha-abc1234`)
  - `{timestamp}` (e.g., `20250120-143022`)
  - `latest` (most recent production build)
  - `v{semver}` if triggered by version tag (e.g., `v1.2.3`)
- Pushes all tags to Google Container Registry / Artifact Registry
- Outputs image URLs in workflow summary

**Duration**: ~8-12 minutes (includes build and push)

### 4. PR Title Validation (`.github/workflows/conventional-commits.yml`)

**Triggers**: Pull request events (opened, edited, synchronize, reopened)
**Purpose**: Enforce Conventional Commits standard
**Validates**: PR titles follow format: `type(scope): description`
**Allowed types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`

**Example valid titles:**
- `feat: add user authentication`
- `fix(api): resolve thread creation race condition`
- `docs: update Railway deployment guide`

## GitHub Secrets Required

Configure these secrets in your GitHub repository settings (Settings → Secrets and variables → Actions):

### For Production Workflow (GKE)
| Secret | Description | Example |
|--------|-------------|---------|
| `GCP_PROJECT_ID` | Google Cloud project ID | `aegra-production` |
| `GCP_SA_KEY` | Service account JSON key | `{"type": "service_account", ...}` |
| `GCR_REGISTRY` | Container registry URL | `us-central1-docker.pkg.dev/PROJECT_ID/aegra` |

**Permissions needed for GCP service account:**
- `roles/artifactregistry.writer` (or `roles/storage.admin` for GCR)

### For E2E Tests (Development + Production)
| Secret | Description |
|--------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM calls in E2E tests |

### Auto-provided
| Secret | Description |
|--------|-------------|
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions |

## Docker Contexts

Aegra uses different Docker configurations for different environments:

### Local Development (`docker-compose.yml`)
- Uses `deployments/docker/Dockerfile`
- Hot-reload enabled via volume mounts
- Development database (PostgreSQL 15)
- Optional Redis service (profile: `redis`)
- Command: `docker compose up aegra`

### Staging (Railway)
- Uses `deployments/docker/Dockerfile` (same as local dev)
- Railway automatically runs migrations on startup
- No hot-reload (production-like)
- Railway managed PostgreSQL

### Production (GKE)
- Uses `deployments/docker/Dockerfile.production`
- Optimized for production:
  - No hot-reload capability
  - HEALTHCHECK instruction for K8s probes
  - Runs migrations in CMD
  - Minimal attack surface
- GCP Cloud SQL for PostgreSQL
