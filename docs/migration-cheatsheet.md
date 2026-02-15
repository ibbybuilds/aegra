# Migration Commands Quick Reference

> **For complete documentation, see [Developer Guide](developer-guide.md)**

> **Note:** As of v0.3.0, migrations run automatically on server startup. You only need Alembic commands for creating new migrations or troubleshooting.

## Essential Commands

```bash
# Create new migration (from repo root)
uv run --package aegra-api alembic revision --autogenerate -m "Description"

# Apply all pending migrations manually (if needed)
uv run --package aegra-api alembic upgrade head

# Rollback last migration
uv run --package aegra-api alembic downgrade -1

# Show migration history
uv run --package aegra-api alembic history

# Show current version
uv run --package aegra-api alembic current
```

## Daily Workflow

**CLI (Recommended):**

```bash
# Start everything (postgres + auto-migrations + hot reload)
aegra dev
```

**Manual:**

```bash
# Start development
docker compose up postgres -d
uv run --package aegra-api alembic upgrade head
uv run --package aegra-api uvicorn aegra_api.main:app --reload
```

## Quick Troubleshooting

| Problem                   | Solution                              |
| ------------------------- | ------------------------------------- |
| Can't connect to database | `docker compose up postgres -d`       |
| Migration fails           | `uv run --package aegra-api alembic current` |
| Database broken           | `uv run --package aegra-api alembic downgrade base` then `alembic upgrade head` |

## Need More Help?

- **[Complete Developer Guide](developer-guide.md)** - Full setup, explanations, and troubleshooting
- **[Alembic Documentation](https://alembic.sqlalchemy.org/)** - Official Alembic docs
