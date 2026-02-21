# PostgreSQL 18 Migration Guide

**Update (Jan 2026):** The database was upgraded from PostgreSQL 15 to 18. This is a **breaking change** for existing local environments.

> **New users:** Simply run `docker compose up` - no action needed.

## Migration Steps (Preserve Data)

### 1. Backup Your Data

While your v15 container is still running:

```bash
docker compose exec -T postgres pg_dumpall -c -U user > dump.sql
```

### 2. Remove Old Volume

The internal file structure changed in v18. You must delete the old volume:

```bash
# Option A: Delete all volumes (simplest)
docker compose down -v

# Option B: Delete only Postgres volume
docker volume rm aegra_postgres_data
```

> ⚠️ Ensure you have the dump from Step 1 before proceeding.

### 3. Start Database Only

Pull changes and start only the database (not the full app):

```bash
git pull origin main
docker compose up -d postgres
```

### 4. Restore Data

Wait a few seconds for the database to initialize, then restore:

```bash
cat dump.sql | docker compose exec -T postgres psql -U user -d postgres
```

### 5. Start Application

```bash
docker compose down
docker compose up -d
```

## Troubleshooting

**Container fails with "database files are incompatible"**

You didn't remove the old volume. Run:

```bash
docker compose down -v
docker compose up -d
```

**Restore fails with "relation already exists"**

The app started before restore and created empty tables. Remove volume and try again from Step 2.
