# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project: Aegra — Open Source LangGraph Backend (Agent Protocol Server)

## Documentation Naming Convention

All documentation files in the `docs/` directory use **kebab-case** naming:
- ✅ `jwt-authentication.md` (correct)
- ✅ `railway-deployment.md` (correct)
- ❌ `JWT_AUTHENTICATION.md` (incorrect)
- ❌ `RailwayDeployment.md` (incorrect)

When creating new documentation, always use kebab-case for consistency.

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

### Redis Management (Required for ava_v1)

```bash
# Redis is automatically started with docker compose up
docker compose up -d

# Check Redis connection
docker compose exec redis redis-cli ping

# Monitor Redis activity (debugging)
docker compose exec redis redis-cli monitor

# Clear Redis cache (testing)
docker compose exec redis redis-cli FLUSHDB
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
- **redis[hiredis]**: In-memory cache for ava_v1 (hotel searches, booking state)

## Authentication System

The server uses environment-based authentication switching with proper LangGraph SDK integration:

**Authentication Types:**

- `AUTH_TYPE=noop` - No authentication (allow all requests, useful for development)
- `AUTH_TYPE=custom` - JWT authentication (production-ready, <1ms latency)

**Configuration:**

```bash
# Set in .env file
AUTH_TYPE=noop  # or "custom"
```

### JWT Authentication

Aegra uses JWT (JSON Web Token) authentication with HS256 symmetric signing for production deployments.

**Key Features:**
- **Sub-1ms latency** for cached tokens (LRU cache with 1000 entries)
- **HMAC-SHA256** signature verification
- **Multi-tenant** user scoping via claims
- **Standard JWT claims** for identity, org, permissions

**Required Environment Variables:**

```bash
# Enable JWT authentication
AUTH_TYPE=custom

# JWT Configuration
AEGRA_JWT_SECRET=<256-bit-secret>           # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
AEGRA_JWT_ISSUER=conversation-relay         # Token issuer (must match between services)
AEGRA_JWT_AUDIENCE=aegra                    # Token audience (must match between services)
AEGRA_JWT_ALGORITHM=HS256                   # Signing algorithm
AEGRA_JWT_VERIFY_EXPIRATION=true            # Validate exp claim
AEGRA_JWT_LEEWAY_SECONDS=30                 # Clock skew tolerance
```

**Token Claims:**

Required:
- `sub` (string): User identifier → maps to `identity`
- `iss` (string): Issuer → must match `AEGRA_JWT_ISSUER`
- `aud` (string): Audience → must match `AEGRA_JWT_AUDIENCE`
- `iat` (number): Issued at timestamp
- `exp` (number): Expiration timestamp

Optional:
- `name` (string): Display name → maps to `display_name`
- `email` (string): Email → maps to `email`
- `org` (string): Organization ID → maps to `org_id`
- `scopes` (array): Permissions → maps to `permissions`

**Generate Test Tokens:**

```bash
# Basic token
uv run python scripts/generate_jwt_token.py --sub test-user

# Full token with all claims
uv run python scripts/generate_jwt_token.py \
  --sub user-123 \
  --name "John Doe" \
  --email "john@example.com" \
  --org "acme-corp" \
  --scopes "read" "write"

# Use token
TOKEN=$(AEGRA_JWT_SECRET=dev-secret AEGRA_JWT_ISSUER=test-issuer AEGRA_JWT_AUDIENCE=test-audience \
  uv run python scripts/generate_jwt_token.py --sub test-user)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/threads
```

**Performance:**
- Cache miss (first verification): 3-5ms
- Cache hit (subsequent): <0.5ms
- Expected hit rate: >80%

**Documentation:**
See [docs/jwt-authentication.md](docs/jwt-authentication.md) for comprehensive guide including:
- Token generation for conversation-relay integration
- Multi-tenant isolation patterns
- Security considerations
- Troubleshooting guide

**Middleware Integration:**
Authentication runs as middleware on every request. LangGraph operations automatically inherit the authenticated user context for proper data scoping.

## ava_v1 Graph Architecture

The ava_v1 graph is a LangChain/LangGraph port of the AVA hotel booking agent.

**Key Features:**
- **State Management**: `active_searches` (label-based tracking), `context_stack` (conversation focus)
- **Redis Caching**: Hotel searches (30 days TTL), room data, booking idempotency (10 min)
- **Dynamic Prompts**: 8-level priority system based on CallContext type
- **Model**: claude-haiku-4-5-20251001 (temperature 0.3)

**Redis Configuration (Required):**
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=  # Empty for local dev
REDIS_DB=0
```

**CallContext Structure (identical to ava):**
```json
{
  "context": {
    "call_context": {
      "type": "general",
      "property": {...},
      "booking": {...},
      "payment": {...},
      "user_phone": "+1234567890"
    }
  }
}
```

**Context Types (5-level priority system):**
- `general`: New conversations (homepage, no specific context)
- `property_specific`: Specific hotel inquiries (Google Ad clicks, direct links to hotel page)
- `dated_property`: Hotel page with dates pre-filled (user clicked "Book Now" with date picker)
- `payment_return`: Post-payment confirmation (redirected after Stripe payment)
- `abandoned_payment`: Payment recovery flows (customer didn't complete payment)

**Setting Context via /state Endpoint:**
```bash
# Example 1: Property-specific context (GA call extension)
POST /threads/{thread_id}/state
{
  "context": {
    "type": "property_specific",
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    }
  }
}

# Example 2: Dated property context
POST /threads/{thread_id}/state
{
  "context": {
    "type": "dated_property",
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    },
    "booking": {
      "destination": "Miami",
      "check_in": "2026-02-01",
      "check_out": "2026-02-03",
      "rooms": 1,
      "adults": 2,
      "children": 0
    }
  }
}

# Example 3: Abandoned payment context
POST /threads/{thread_id}/state
{
  "context": {
    "type": "abandoned_payment",
    "abandoned_payment": {
      "timestamp": "2026-01-22T10:25:00Z",
      "amount": 299.99,
      "currency": "USD",
      "minutes_ago": 10,
      "reason": "timeout"
    }
  }
}
```

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

### Required for All Workflows
| Secret | Description | How to Create |
|--------|-------------|---------------|
| `GH_PAT` | Personal Access Token for private repo access | GitHub Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token → Select `repo` scope |

**Note**: This token is required because `ava-core` is a private dependency. The token must have `repo` scope to clone private repositories.

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
