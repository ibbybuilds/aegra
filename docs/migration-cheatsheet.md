# Migration Commands Quick Reference

> **For complete documentation, see [Developer Guide](developer-guide.md)**

> **Note:** As of v0.3.0, migrations run automatically on server startup. You only need these commands for creating new migrations or troubleshooting.

## Essential Commands

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
aegra db upgrade
uv run --package aegra-api uvicorn aegra_api.main:app --reload

# Make database changes
uv run --package aegra-api alembic revision --autogenerate -m "Add new feature"
aegra db upgrade
```

## Quick Troubleshooting

| Problem                   | Solution                              |
| ------------------------- | ------------------------------------- |
| Can't connect to database | `docker compose up postgres -d`       |
| Migration fails           | `aegra db current`                    |
| Database broken           | `aegra db downgrade base` then `aegra db upgrade` |

## Need More Help?

- **[Complete Developer Guide](developer-guide.md)** - Full setup, explanations, and troubleshooting
- **[Alembic Documentation](https://alembic.sqlalchemy.org/)** - Official Alembic docs
