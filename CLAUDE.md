# CLAUDE.md

Guidance for Claude Code when working with this repository.

Project: Aegra — Open Source LangGraph Backend (Agent Protocol Server)

## Conventions

- Documentation files use kebab-case: `jwt-authentication.md`, not `JWT_AUTHENTICATION.md`
- Imports: Relative within package, absolute for external dependencies
- Run `uv run pytest` before completing tasks

## Quick Start

```bash
# Setup
uv install
source .venv/bin/activate  # Required for migrations

# Docker (all-in-one)
docker compose up aegra

# Local development
docker compose up postgres -d
python3 scripts/migrate.py upgrade
uv run uvicorn src.agent_server.main:app --reload

# Testing
uv run pytest
uv run pytest --cov=src --cov-report=html
curl http://localhost:8000/health

# Migrations (activate venv first)
python3 scripts/migrate.py upgrade
python3 scripts/migrate.py revision --autogenerate -m "description"
python3 scripts/migrate.py current

# Redis (for ava_v1)
docker compose up -d  # Auto-starts Redis
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli FLUSHDB  # Clear cache
```

## Architecture

Aegra is an Agent Protocol server that wraps LangGraph packages. LangGraph handles state persistence and graph execution; FastAPI provides Agent Protocol compliance.

### Database

- **LangGraph state**: `AsyncPostgresSaver` (checkpoints) and `AsyncPostgresStore` (long-term memory)
- **SQLAlchemy metadata**: Agent Protocol tables (assistants, runs, thread_metadata)
- **URL formats**: LangGraph uses `postgresql://`, SQLAlchemy uses `postgresql+asyncpg://`
- **DatabaseManager** (src/agent_server/core/database.py): Handles URL conversion, provides singleton access to components

### Configuration

**aegra.json** defines graphs and auth:
```json
{
  "graphs": {"weather_agent": "./graphs/weather_agent.py:graph"},
  "auth": {"path": "./auth.py:auth"}
}
```

**auth.py** uses LangGraph SDK Auth:
- `@auth.authenticate` for user authentication
- `@auth.on.{resource}.{action}` for authorization
- Returns `Auth.types.MinimalUserDict`

### Graphs

Agents export a compiled `graph` variable:
```python
workflow = StateGraph(WeatherState)
# ... define nodes/edges
graph = workflow.compile()  # Must export as 'graph'
```

### FastAPI

- **Lifespan**: `@asynccontextmanager` initializes/cleanups LangGraph components
- **Health**: Tests SQLAlchemy engine, checkpointer, and store connectivity
- **Auth**: Middleware validates token, filters data by user context (multi-tenant)

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

## Authentication

**Types:**
- `AUTH_TYPE=noop`: No authentication (development)
- `AUTH_TYPE=custom`: JWT authentication (<1ms latency, production-ready)

**JWT Setup:**
```bash
AUTH_TYPE=custom
AEGRA_JWT_SECRET=<256-bit-secret>  # python -c "import secrets; print(secrets.token_urlsafe(32))"
AEGRA_JWT_ISSUER=conversation-relay
AEGRA_JWT_AUDIENCE=aegra
AEGRA_JWT_ALGORITHM=HS256
```

**Generate tokens:**
```bash
uv run python scripts/generate_jwt_token.py --sub test-user --name "John Doe" --org "acme-corp"
```

See [docs/jwt-authentication.md](docs/jwt-authentication.md) for complete guide.

## ava_v1 Graph

Hotel booking agent (LangGraph port of AVA).

**Features:**
- State: `active_searches`, `context_stack`
- Redis: Hotel searches (30d TTL), room data, booking idempotency (10m)
- Model: claude-haiku-4-5-20251001 (temperature 0.3)

**Redis Config:**
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

**Context Types (priority system):**
- `general`: New conversations
- `property_specific`: Hotel-specific inquiries
- `dated_property`: Pre-filled dates
- `payment_return`: Post-payment confirmation
- `abandoned_payment`: Payment recovery

**Set via POST /threads/{thread_id}/state:**
```json
{
  "context": {
    "type": "property_specific",
    "property": {"property_name": "JW Marriott Miami", "hotel_id": "123abc"}
  }
}
```

## Development Patterns

- **Database**: Use `db_manager.get_checkpointer()`, `db_manager.get_store()`, `db_manager.get_engine()`
- **Auth**: Use `get_current_user(request)` dependency; errors via `Auth.exceptions.HTTPException`
- **Testing**: Async-aware with pytest-asyncio
- **Migrations**: Alembic-managed (activate venv first); Docker auto-runs on startup

## Deployment

### Staging (Railway)
- **Branch**: `development` (auto-deploys)
- **Workflow**: Push → CI (`.github/workflows/development-ci.yml`) → Railway deploys
- **Database**: Railway PostgreSQL
- **Config**: See `.env.staging.example` and [docs/railway-deployment.md](docs/railway-deployment.md)

### Production (GKE)
- **Branch**: `main` (manual deploy)
- **Workflow**: Push/tag → CI + E2E → Build image → Push to GCR → Manual K8s update
- **Database**: GCP Cloud SQL PostgreSQL
- **Config**: See `.env.production.example` and [docs/gke-deployment.md](docs/gke-deployment.md)
- **Secrets**: `GCP_PROJECT_ID`, `GCP_SA_KEY`, `GCR_REGISTRY`

## CI/CD

**Feature Branch** (`.github/workflows/ci.yml`): Ruff, Bandit, MyPy, unit tests (~2-3 min)

**Development** (`.github/workflows/development-ci.yml`): Feature checks + E2E + migrations (~5-8 min) → Railway auto-deploys

**Production** (`.github/workflows/production.yml`): Dev checks + build + push to GCR (~8-12 min)
- Tags: `sha-{hash}`, `{timestamp}`, `latest`, `v{semver}` (if tag)

**PR Validation** (`.github/workflows/conventional-commits.yml`): Enforces `type(scope): description`

## GitHub Secrets

**All workflows:**
- `GH_PAT`: Personal access token with `repo` scope (for private `ava-core` dependency)
- `OPENAI_API_KEY`: For E2E tests

**Production (GKE):**
- `GCP_PROJECT_ID`, `GCP_SA_KEY` (needs `roles/artifactregistry.writer`), `GCR_REGISTRY`

## Docker

- **Local**: `docker-compose.yml` → `deployments/docker/Dockerfile` (hot-reload)
- **Staging**: Railway uses same Dockerfile as local (no hot-reload)
- **Production**: `deployments/docker/Dockerfile.production` (optimized, HEALTHCHECK for K8s)
