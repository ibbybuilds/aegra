# Aegra Developer Guide

Welcome to Aegra! This guide will help you get started with development, whether you're a newcomer to database migrations or an experienced developer.

## 📋 Table of Contents

- [🚀 Quick Start for New Developers](#-quick-start-for-new-developers)
- [✨ Code Quality & Standards](#-code-quality--standards)
- [📚 Understanding Database Migrations](#-understanding-database-migrations)
- [🔧 Database Migration Commands](#-database-migration-commands)
- [🛠️ Development Workflow](#️-development-workflow)
- [📁 Project Structure](#-project-structure)
- [🔍 Understanding Migration Files](#-understanding-migration-files)
- [🚨 Common Issues & Solutions](#-common-issues--solutions)
- [🧪 Testing Your Changes](#-testing-your-changes)
- [🚀 Production Deployment](#-production-deployment)
- [📖 Best Practices](#-best-practices)
- [🔗 Useful Resources](#-useful-resources)
- [🆘 Getting Help](#-getting-help)
- [📋 Quick Reference](#-quick-reference)

## 🚀 Quick Start for New Developers

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
uv sync

# 2. Activate environment (IMPORTANT!)
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows

# 3. Start everything (database + migrations + server)
docker compose up aegra
```

🎉 **You're ready to develop!** Visit http://localhost:8000/docs to see the API.

## ✨ Code Quality & Standards

Aegra uses automated code quality enforcement to maintain high standards and consistency.

### Setup

**Option 1: Using Make (Recommended - installs hooks automatically)**

```bash
make dev-install     # Installs dependencies + git hooks
```

**Option 2: Using uv directly**

```bash
uv sync
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

The hooks will check your code before every commit.

### What Gets Checked Automatically

When you commit, these checks run automatically:

- ✅ **Code formatting** (Ruff) - Auto-formats your code
- ✅ **Linting** (Ruff) - Checks code quality
- ✅ **Type checking** (mypy) - Validates type hints
- ✅ **Security** (Bandit) - Scans for vulnerabilities
- ✅ **Commit message** - Enforces format

### Commit Message Format

**Required format:** `type(scope): description`

```bash
# Good examples ✅
git commit -m "feat: add user authentication"
git commit -m "fix(api): resolve rate limiting bug"
git commit -m "docs: update installation guide"

# Bad examples ❌
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

📖 **For detailed information**, see:

- [Code Quality Quick Reference](code-quality.md) - Commands and troubleshooting
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Complete contribution guide

## 📚 Understanding Database Migrations

### What are Database Migrations?

Think of migrations as **version control for your database structure**. Instead of manually creating tables, you write scripts that:

- Create tables, columns, and indexes
- Can be applied in order
- Can be rolled back if needed
- Are tracked in version control

### Why We Use Alembic

- **Industry Standard**: Used by most Python projects
- **Safe**: Can rollback changes
- **Team-Friendly**: Everyone gets the same database structure
- **Production-Ready**: Tested migration process

## 🔧 Database Migration Commands

### Using Our Custom Script (Recommended)

**⚠️ Important**: Make sure your virtual environment is activated before running migration commands:

```bash
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows
```

We've created a convenient script that wraps Alembic commands:

```bash
# Apply all pending migrations
python3 scripts/migrate.py upgrade

# Create a new migration
python3 scripts/migrate.py revision --autogenerate -m "Add user preferences"

# Rollback last migration
python3 scripts/migrate.py downgrade

# Show migration history
python3 scripts/migrate.py history

# Show current version
python3 scripts/migrate.py current

# Reset database (⚠️ destructive - drops all data)
python3 scripts/migrate.py reset
```

### Direct Alembic Commands

If you prefer using Alembic directly:

```bash
# Apply migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# Rollback
alembic downgrade -1

# Show history
alembic history
```

## 🛠️ Development Workflow

### Option 1: Docker Development (Recommended for Beginners)

```bash
# Start everything (database + migrations + server)
docker compose up aegra

# Or start in background
docker compose up -d aegra
```

**Benefits:**

- ✅ One command to start everything
- ✅ Migrations run automatically
- ✅ Consistent environment
- ✅ Production-like setup

### Option 2: Local Development (Recommended for Advanced Users)

```bash
# 1. Start database
docker compose up postgres -d

# 2. Apply any new migrations
python3 scripts/migrate.py upgrade

# 3. Start development server
python3 run_server.py
```

**Benefits:**

- ✅ Full control over each component
- ✅ Easier debugging
- ✅ Faster development cycle
- ✅ Direct access to logs

### Making Database Changes

When you need to change the database structure:

```bash
# 1. Make changes to your code/models

# 2. Generate migration
python3 scripts/migrate.py revision --autogenerate -m "Add new feature"

# 3. Review the generated migration file
# Check: alembic/versions/XXXX_add_new_feature.py

# 4. Apply the migration
python3 scripts/migrate.py upgrade

# 5. Test your changes
python3 run_server.py
```

### Testing Migrations

```bash
# Test upgrade path
python3 scripts/migrate.py reset  # Start fresh
python3 scripts/migrate.py upgrade  # Apply all

# Test downgrade path
python3 scripts/migrate.py downgrade  # Rollback one
python3 scripts/migrate.py upgrade    # Apply again
```

## 📁 Project Structure

```
aegra/
├── alembic/                    # Database migrations
│   ├── versions/              # Migration files
│   ├── env.py                 # Alembic configuration
│   └── script.py.mako         # Migration template
├── src/agent_server/          # Main application code
│   ├── core/database.py       # Database connection
│   ├── api/                   # API endpoints
│   ├── services/              # Core services (LangGraph, etc.)
│   └── models/                # Data models
├── scripts/
│   └── migrate.py             # Migration helper script
├── docs/
│   ├── developer-guide.md     # This file
│   └── migrations.md          # Detailed migration docs
├── alembic.ini                # Alembic configuration
└── docker compose.yml         # Database setup
```

## 🔄 LangGraph Service Architecture

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

## 🔍 Understanding Migration Files

### Migration File Structure

Each migration file in `alembic/versions/` contains:

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

## 🚨 Common Issues & Solutions

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
python3 scripts/migrate.py upgrade
python3 run_server.py
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
python3 scripts/migrate.py current

# If needed, reset and reapply
python3 scripts/migrate.py reset
```

**Problem**: Migration conflicts

```bash
# Solution: Check migration history
python3 scripts/migrate.py history

# Reset if needed (⚠️ destructive)
python3 scripts/migrate.py reset
```

### Permission Issues

**Problem**: "Permission denied" on migration script

```bash
# Solution: Make script executable
chmod +x scripts/migrate.py
```

## 🧪 Testing Your Changes

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api/test_assistants.py

# Run with coverage
pytest --cov=src/agent_server
```

### Testing Database Changes

```bash
# 1. Create a test migration
python3 scripts/migrate.py revision --autogenerate -m "Test feature"

# 2. Apply it
python3 scripts/migrate.py upgrade

# 3. Test your application
python3 run_server.py

# 4. If something breaks, rollback
python3 scripts/migrate.py downgrade
```

## 🚀 Production Deployment

### Before Deploying

1. **Test migrations on staging**:

   ```bash
   # Apply to staging database
   python3 scripts/migrate.py upgrade
   ```

2. **Backup production database**:

   ```bash
   # Always backup before migrations
   pg_dump your_database > backup.sql
   ```

3. **Deploy with migrations**:
   ```bash
   # Docker automatically runs migrations
   docker compose up aegra
   ```

### Monitoring

```bash
# Check migration status
python3 scripts/migrate.py current

# View migration history
python3 scripts/migrate.py history
```

## 📖 Best Practices

### Creating Migrations

1. **Always use autogenerate** when possible:

   ```bash
   python3 scripts/migrate.py revision --autogenerate -m "Descriptive message"
   ```

2. **Review generated migrations**:

   - Check the SQL that will be executed
   - Ensure it matches your intent
   - Test on a copy of production data

3. **Use descriptive messages**:

   ```bash
   # Good
   python3 scripts/migrate.py revision --autogenerate -m "Add user preferences table"

   # Bad
   python3 scripts/migrate.py revision --autogenerate -m "fix"
   ```

### Code Organization

1. **Keep migrations small**: One logical change per migration
2. **Test migrations**: Always test upgrade and downgrade paths
3. **Document changes**: Use clear migration messages
4. **Version control**: Commit migration files with your code changes

## 🔗 Useful Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Agent Protocol Specification](https://github.com/langchain-ai/agent-protocol)

## 🆘 Getting Help

### When You're Stuck

1. **Check the logs**:

   ```bash
   docker compose logs postgres
   ```

2. **Verify database state**:

   ```bash
   python3 scripts/migrate.py current
   python3 scripts/migrate.py history
   ```

3. **Reset if needed** (⚠️ destructive):

   ```bash
   python3 scripts/migrate.py reset
   ```

4. **Ask for help**:
   - Check existing issues on GitHub
   - Create a new issue with details
   - Join our community discussions

### Common Questions

**Q: Do I need to run migrations every time I start development?**
A: Only if there are new migrations. The Docker setup automatically runs them.

**Q: What if I accidentally break the database?**
A: Use `python3 scripts/migrate.py reset` to start fresh (⚠️ loses all data).

**Q: How do I know what migrations are pending?**
A: Use `python3 scripts/migrate.py history` to see all migrations and their status.

**Q: Can I modify an existing migration?**
A: Generally no - create a new migration instead. Modifying existing migrations can cause issues.

---

🎉 **You're now ready to contribute to Aegra!**

Start with small changes, test your migrations, and don't hesitate to ask for help. Happy coding!

---

## 📋 Quick Reference

### Essential Commands

```bash
# Apply all pending migrations
python3 scripts/migrate.py upgrade

# Create new migration
python3 scripts/migrate.py revision --autogenerate -m "Description"

# Rollback last migration
python3 scripts/migrate.py downgrade

# Show migration history
python3 scripts/migrate.py history

# Show current version
python3 scripts/migrate.py current

# Reset database (⚠️ DESTRUCTIVE - loses all data)
python3 scripts/migrate.py reset
```

### Daily Development Workflow

**Docker (Recommended):**

```bash
# Start everything
docker compose up aegra
```

**Local Development:**

```bash
# Start database
docker compose up postgres -d

# Apply migrations
python3 scripts/migrate.py upgrade

# Start server
python3 run_server.py
```

### Common Patterns

**Adding a New Table:**

```bash
python3 scripts/migrate.py revision --autogenerate -m "Add users table"
python3 scripts/migrate.py upgrade
```

**Adding a Column:**

```bash
python3 scripts/migrate.py revision --autogenerate -m "Add email to users"
python3 scripts/migrate.py upgrade
```

**Testing Migrations:**

```bash
python3 scripts/migrate.py reset
python3 scripts/migrate.py upgrade
```

### Troubleshooting Quick Reference

| Problem                   | Solution                                                                        |
| ------------------------- | ------------------------------------------------------------------------------- |
| **Incompatible DB version** | **See [PostgreSQL 18 Migration Guide](postgres-18-migration.md)** |
| Can't connect to database | `docker compose up postgres -d`       |
| Migration fails           | `python3 scripts/migrate.py current`  |
| Permission denied         | `chmod +x scripts/migrate.py`         |
| Database broken           | `python3 scripts/migrate.py reset` ⚠️ |

### Environment Setup

**For Docker Development:**

```bash
# Activate virtual environment (IMPORTANT!)
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows

# Install dependencies
uv sync

# Start everything
docker compose up aegra
```

**For Local Development:**

```bash
# Activate virtual environment (IMPORTANT!)
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows

# Install dependencies
uv sync

# Start database
docker compose up postgres -d

# Apply migrations
python3 scripts/migrate.py upgrade
```
