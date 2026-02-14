# Aegra Developer Guide

Welcome to Aegra! This guide will help you get started with development, whether you're a newcomer to database migrations or an experienced developer.

## Table of Contents

- [Quick Start for New Developers](#quick-start-for-new-developers)
- [Code Quality & Standards](#code-quality--standards)
- [Understanding Database Migrations](#understanding-database-migrations)
- [Database Migration Commands](#database-migration-commands)
- [Development Workflow](#development-workflow)
- [Project Structure](#project-structure)
- [Understanding Migration Files](#understanding-migration-files)
- [Common Issues & Solutions](#common-issues--solutions)
- [Testing Your Changes](#testing-your-changes)
- [Production Deployment](#production-deployment)
- [Best Practices](#best-practices)
- [Useful Resources](#useful-resources)
- [Getting Help](#getting-help)
- [Quick Reference](#quick-reference)

## Quick Start for New Developers

### Prerequisites

- Python 3.11+
- Docker
- Git
- uv (Python package manager)

### First Time Setup (5 minutes)

```bash
# 1. Clone and setup
git clone https://github.com/ibbybuilds/aegra.git
cd aegra
uv sync --all-packages

# 2. Start the development server (starts PostgreSQL + auto-migrates + hot reload)
aegra dev
```

You're ready to develop! Visit http://localhost:8000/docs to see the API.

> **Note:** `aegra dev` automatically starts PostgreSQL, applies any pending database migrations, and launches the server with hot reload. No manual migration step needed.

### Using the CLI

```bash
# Install the CLI
pip install aegra-cli

# Initialize a new project (interactive template selection)
aegra init ./my-agent
cd my-agent

# Or non-interactive
# aegra init ./my-agent -t 1 -n "My Agent"

# Install dependencies and start development server
uv sync
uv run aegra dev
```

## Code Quality & Standards

Aegra uses automated code quality enforcement to maintain high standards and consistency.

### Setup

**Option 1: Using Make (Recommended - installs hooks automatically)**

```bash
make dev-install     # Installs dependencies + git hooks
```

**Option 2: Using uv directly**

```bash
uv sync --all-packages
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

The hooks will check your code before every commit.

### What Gets Checked Automatically

When you commit, these checks run automatically:

- **Code formatting** (Ruff) - Auto-formats your code
- **Linting** (Ruff) - Checks code quality
- **Type checking** (mypy) - Validates type hints
- **Security** (Bandit) - Scans for vulnerabilities
- **Commit message** - Enforces format

### Commit Message Format

**Required format:** `type(scope): description`

```bash
# Good examples
git commit -m "feat: add user authentication"
git commit -m "fix(api): resolve rate limiting bug"
git commit -m "docs: update installation guide"

# Bad examples
git commit -m "fixed stuff"
git commit -m "WIP"
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

### Useful Commands

```bash
make format        # Auto-format code
make lint          # Check code quality
make type-check    # Run type checking
make test          # Run tests
make test-cov      # Tests with coverage
make ci-check      # Run all CI checks locally
```

### Before Committing

```bash
# Quick check before committing
make format  # Auto-fix issues
make test    # Verify tests pass

# Or run everything at once
make ci-check
```

For detailed information, see:

- [Code Quality Quick Reference](code-quality.md) - Commands and troubleshooting
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Complete contribution guide

## Understanding Database Migrations

### What are Database Migrations?

Think of migrations as **version control for your database structure**. Instead of manually creating tables, you write scripts that:

- Create tables, columns, and indexes
- Can be applied in order
- Can be rolled back if needed
- Are tracked in version control

### Auto-Migrations on Startup

**As of v0.3.0, Aegra automatically applies pending migrations when the server starts.** You do not need to run migrations manually for normal development. The server runs `alembic upgrade head` during startup before initializing the database.

This means:
- `aegra dev` applies migrations automatically
- Docker deployments apply migrations automatically
- You only need manual migration commands when **creating new migrations** or **troubleshooting**

### Why We Use Alembic

- **Industry Standard**: Used by most Python projects
- **Safe**: Can rollback changes
- **Team-Friendly**: Everyone gets the same database structure
- **Production-Ready**: Tested migration process

## Database Migration Commands

### Using the CLI (Recommended)

```bash
# Apply all pending migrations
aegra db upgrade

# Create a new migration (from repo root)
uv run --package aegra-api alembic revision --autogenerate -m "Add user preferences"

# Rollback last migration
aegra db downgrade

# Show migration history
aegra db history

# Show current version
aegra db current
```

### Direct Alembic Commands

If you prefer using Alembic directly (from repo root):

```bash
# Apply migrations
uv run --package aegra-api alembic upgrade head

# Create new migration
uv run --package aegra-api alembic revision --autogenerate -m "Description"

# Rollback
uv run --package aegra-api alembic downgrade -1

# Show history
uv run --package aegra-api alembic history
```

## Development Workflow

### Option 1: CLI Development (Recommended)

```bash
# Start everything (database + auto-migrations + server with hot reload)
aegra dev
```

**Benefits:**

- One command to start everything
- Migrations run automatically on startup
- Hot reload on code changes
- Docker PostgreSQL managed for you

### Option 2: Docker Compose Development

```bash
# Start everything with Docker
docker compose up aegra
```

**Benefits:**

- Fully containerized
- Consistent environment
- Production-like setup

### Option 3: Manual Development

```bash
# 1. Start database
docker compose up postgres -d

# 2. Apply any new migrations
aegra db upgrade

# 3. Start development server
uv run --package aegra-api uvicorn aegra_api.main:app --reload
```

**Benefits:**

- Full control over each component
- Easier debugging
- Direct access to logs

### Making Database Changes

When you need to change the database structure:

```bash
# 1. Make changes to your ORM models in libs/aegra-api/src/aegra_api/core/orm.py

# 2. Generate migration
uv run --package aegra-api alembic revision --autogenerate -m "Add new feature"

# 3. Review the generated migration file
# Check: libs/aegra-api/alembic/versions/XXXX_add_new_feature.py

# 4. Apply the migration
aegra db upgrade

# 5. Restart the server to pick up changes
aegra dev
```

### Testing Migrations

```bash
# Test upgrade path
aegra db downgrade base   # Rollback all
aegra db upgrade          # Apply all

# Test downgrade path
aegra db downgrade        # Rollback one
aegra db upgrade          # Apply again
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
│   └── subgraph_hitl_agent/          # Hierarchical with HITL
│
├── docs/                             # Documentation
├── deployments/                      # Docker configs
├── aegra.json                        # Agent graph definitions
└── docker-compose.yml                # Local development setup
```

## LangGraph Service Architecture

The `LangGraphService` is the core component that manages graph loading, caching, and execution.

### Design Principles

1. **Cache base graphs, not execution instances**: We cache the compiled graph structure (without checkpointer/store) for fast loading
2. **Fresh copies per-request**: Each execution gets a fresh graph copy with checkpointer/store injected
3. **Thread-safe by design**: No locks needed because cached state is immutable

### Usage Patterns

**For graph execution** (runs, state operations):
```python
# Use context manager - yields fresh graph with checkpointer/store
async with langgraph_service.get_graph(graph_id) as graph:
    async for event in graph.astream(input, config):
        ...
```

**For validation/schema extraction** (no execution needed):
```python
# Use simple async method - returns base graph without checkpointer/store
graph = await langgraph_service.get_graph_for_validation(graph_id)
schemas = extract_schemas(graph)
```

### Why This Pattern?

| Old Pattern (with locks) | New Pattern (context manager) |
|-------------------------|------------------------------|
| Single cached instance with checkpointer | Fresh copy per request |
| Needed locks for concurrent access | Thread-safe by design |
| Potential race conditions | No race conditions possible |
| More complex error handling | Simple, predictable behavior |

Each request gets its own graph copy, ensuring isolation and thread-safety.

## Understanding Migration Files

### Migration File Structure

Each migration file in `libs/aegra-api/alembic/versions/` contains:

```python
"""Add user preferences table

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # This runs when applying the migration
    op.create_table('user_preferences',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('theme', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )

def downgrade() -> None:
    # This runs when rolling back the migration
    op.drop_table('user_preferences')
```

### Key Concepts

- **Revision ID**: Unique identifier for the migration
- **Revises**: Points to the previous migration
- **upgrade()**: What to do when applying the migration
- **downgrade()**: What to do when rolling back the migration

## Common Issues & Solutions

### Database Version Upgrade (Postgres 15 -> 18)

**Problem**: Container fails with `FATAL: database files are incompatible with server`

This happens because we upgraded to PostgreSQL 18, but your Docker volume still contains data formatted for PostgreSQL 15.

**Solution**:
You need to remove the old volume and (optionally) restore your data.
Please follow the **[PostgreSQL 18 Migration Guide](postgres-18-migration.md)**.

### Migration Issues in Docker

**Problem**: Migration fails in Docker container

```bash
# Solution: Check container logs
docker compose logs aegra

# Solution: Run migrations manually for debugging
docker compose up postgres -d
aegra db upgrade
```

**Problem**: Database connection issues in Docker

```bash
# Solution: Check if database is ready
docker compose ps postgres

# Solution: Restart database
docker compose restart postgres
```

### Database Connection Issues

**Problem**: Can't connect to database

```bash
# Solution: Start the database
docker compose up postgres -d
```

**Problem**: Migration fails with connection error

```bash
# Solution: Check if database is running
docker compose ps postgres

# If not running, start it
docker compose up postgres -d
```

### Migration Issues

**Problem**: "No such revision" error

```bash
# Solution: Check current state
aegra db current

# If needed, downgrade to base and reapply
aegra db downgrade base
aegra db upgrade
```

**Problem**: Migration conflicts

```bash
# Solution: Check migration history
aegra db history

# Downgrade to base and reapply if needed (loses all data)
aegra db downgrade base
aegra db upgrade
```

## Testing Your Changes

### Running Tests

```bash
# Run all tests (or use: make test)
uv run --package aegra-api pytest libs/aegra-api/tests/
uv run --package aegra-cli pytest libs/aegra-cli/tests/

# Run specific test file
uv run --package aegra-api pytest libs/aegra-api/tests/unit/test_api/test_assistants.py

# Run with coverage (or use: make test-cov)
uv run --package aegra-api pytest libs/aegra-api/tests/ --cov=libs/aegra-api/src --cov-report=html
```

### Testing Database Changes

```bash
# 1. Create a test migration
uv run --package aegra-api alembic revision --autogenerate -m "Test feature"

# 2. Apply it
aegra db upgrade

# 3. Test your application
aegra dev

# 4. If something breaks, rollback
aegra db downgrade
```

## Production Deployment

### Before Deploying

1. **Test migrations on staging**:

   ```bash
   aegra db upgrade
   ```

2. **Backup production database**:

   ```bash
   # Always backup before migrations
   pg_dump your_database > backup.sql
   ```

3. **Deploy**:
   ```bash
   # Migrations run automatically on server startup
   docker compose up aegra
   ```

### Monitoring

```bash
# Check migration status
aegra db current

# View migration history
aegra db history
```

## Best Practices

### Creating Migrations

1. **Always use autogenerate** when possible:

   ```bash
   uv run --package aegra-api alembic revision --autogenerate -m "Descriptive message"
   ```

2. **Review generated migrations**:

   - Check the SQL that will be executed
   - Ensure it matches your intent
   - Test on a copy of production data

3. **Use descriptive messages**:

   ```bash
   # Good
   uv run --package aegra-api alembic revision --autogenerate -m "Add user preferences table"

   # Bad
   uv run --package aegra-api alembic revision --autogenerate -m "fix"
   ```

### Code Organization

1. **Keep migrations small**: One logical change per migration
2. **Test migrations**: Always test upgrade and downgrade paths
3. **Document changes**: Use clear migration messages
4. **Version control**: Commit migration files with your code changes

## Useful Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Agent Protocol Specification](https://github.com/langchain-ai/agent-protocol)

## Getting Help

### When You're Stuck

1. **Check the logs**:

   ```bash
   docker compose logs postgres
   ```

2. **Verify database state**:

   ```bash
   aegra db current
   aegra db history
   ```

3. **Ask for help**:
   - Check existing issues on GitHub
   - Create a new issue with details
   - Join our community discussions

### Common Questions

**Q: Do I need to run migrations every time I start development?**
A: No. As of v0.3.0, migrations run automatically when the server starts via `aegra dev` or Docker.

**Q: What if I accidentally break the database?**
A: Use `aegra db downgrade base` to rollback all migrations, then `aegra db upgrade` to reapply (this loses all data).

**Q: How do I know what migrations are pending?**
A: Use `aegra db history` to see all migrations and their status.

**Q: Can I modify an existing migration?**
A: Generally no - create a new migration instead. Modifying existing migrations can cause issues.

---

You're now ready to contribute to Aegra!

Start with small changes, test your migrations, and don't hesitate to ask for help. Happy coding!

---

## Quick Reference

### Essential Commands

```bash
# Apply all pending migrations
aegra db upgrade

# Create new migration
uv run --package aegra-api alembic revision --autogenerate -m "Description"

# Rollback last migration
aegra db downgrade

# Show migration history
aegra db history

# Show current version
aegra db current
```

### Daily Development Workflow

**CLI (Recommended):**

```bash
# Start everything (postgres + auto-migrations + hot reload)
aegra dev
```

**Local Development:**

```bash
# Start database
docker compose up postgres -d

# Apply migrations
aegra db upgrade

# Start server
uv run --package aegra-api uvicorn aegra_api.main:app --reload
```

### Common Patterns

**Adding a New Table:**

```bash
uv run --package aegra-api alembic revision --autogenerate -m "Add users table"
aegra db upgrade
```

**Adding a Column:**

```bash
uv run --package aegra-api alembic revision --autogenerate -m "Add email to users"
aegra db upgrade
```

**Testing Migrations:**

```bash
aegra db downgrade base
aegra db upgrade
```

### Troubleshooting Quick Reference

| Problem                   | Solution                                                                        |
| ------------------------- | ------------------------------------------------------------------------------- |
| **Incompatible DB version** | **See [PostgreSQL 18 Migration Guide](postgres-18-migration.md)** |
| Can't connect to database | `docker compose up postgres -d`       |
| Migration fails           | `aegra db current`                    |
| Database broken           | `aegra db downgrade base` then `aegra db upgrade` |

### Environment Setup

```bash
# Install all workspace dependencies
uv sync --all-packages

# Start development server
aegra dev
```
