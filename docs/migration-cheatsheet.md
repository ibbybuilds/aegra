# Migration Commands Quick Reference

> **📚 For complete documentation, see [Developer Guide](developer-guide.md)**

**⚠️ Important**: Always activate your virtual environment first:

```bash
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows
```

## 🛠️ Daily Workflow

**Docker (Recommended):**

```bash
# Start everything
docker compose up aegra
```

**Local Development:**

```bash
# Start development
docker compose up postgres -d
aegra migrate upgrade
aegra dev

# Make database changes
aegra migrate revision "Add new feature"
aegra migrate upgrade
```

## 🔍 Quick Troubleshooting

| Problem                   | Solution                              |
| ------------------------- | ------------------------------------- |
| Can't connect to database | `docker compose up postgres -d`       |
| Migration fails           | `aegra migrate current`               |
| Database broken           | `aegra migrate reset` ⚠️              |

## 📚 Need More Help?

- **📖 [Complete Developer Guide](developer-guide.md)** - Full setup, explanations, and troubleshooting
- **🔗 [Alembic Documentation](https://alembic.sqlalchemy.org/)** - Official Alembic docs
