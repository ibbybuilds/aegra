# Deployment Guide

This guide covers how to deploy Aegra in different environments, from local development to production.

## CLI Commands Overview

Aegra provides three ways to run the server, each designed for a different scenario:

| Command | Starts PostgreSQL? | Starts App? | Environment |
|---|---|---|---|
| `aegra dev` | Yes (Docker) | Yes (host, hot reload) | Local development |
| `aegra up` | Yes (Docker) | Yes (Docker) | Self-hosted production |
| `aegra serve` | No | Yes (host) | PaaS, containers, bare metal |

### `aegra dev` — Local Development

Starts a PostgreSQL container via Docker Compose and runs the app on your host with hot reload. This is the recommended way to develop locally.

```bash
aegra dev
```

What it does:
1. Finds or generates `docker-compose.yml` with PostgreSQL
2. Starts the PostgreSQL container
3. Loads your `.env` file
4. Runs `uvicorn` with `--reload` for hot reloading
5. Migrations apply automatically on startup

Options:
- `--host` — Host to bind to (default: `127.0.0.1`)
- `--port` — Port to bind to (default: `8000`)
- `--config` / `-c` — Path to aegra.json (auto-detected by default)
- `--env-file` / `-e` — Path to .env file (default: `.env` in current directory)
- `--file` / `-f` — Path to docker-compose.yml
- `--no-db-check` — Skip database readiness check

### `aegra up` — Docker Production Deployment

Starts the entire stack (PostgreSQL + app) in Docker containers. This is the recommended way to deploy on your own infrastructure.

```bash
aegra up
```

What it does:
1. Finds or generates `docker-compose.yml` with PostgreSQL + app service
2. Builds the Docker image from your `Dockerfile`
3. Starts all containers
4. The app container runs `aegra serve` internally
5. Migrations apply automatically on startup

Options:
- `--build/--no-build` — Build images before starting (default: build is ON)
- `--file` / `-f` — Path to a custom compose file
- `SERVICE...` — Specific services to start

To stop:
```bash
aegra down            # Stop containers
aegra down --volumes  # Stop and remove data volumes
```

### `aegra serve` — Direct Server (No Docker)

Runs the uvicorn server directly on the host. Does **not** start PostgreSQL — you must provide a running database.

```bash
aegra serve
```

What it does:
1. Loads your `.env` file
2. Runs `uvicorn` in production mode (no reload)
3. Migrations apply automatically on startup
4. Connects to whatever database is configured in `DATABASE_URL` or `POSTGRES_*` vars

Options:
- `--host` — Host to bind to (default: `0.0.0.0`)
- `--port` — Port to bind to (default: from env or `8000`)
- `--config` / `-c` — Path to aegra.json

When to use:
- **Inside Docker containers** — the generated `Dockerfile` uses `aegra serve` as its CMD
- **PaaS platforms** (Railway, Render, Fly.io) — they run the process directly, database is a managed addon
- **Bare metal / VM** — when PostgreSQL runs elsewhere (RDS, Supabase, Neon, etc.)
- **Kubernetes** — define the command in your pod spec

## Deployment Scenarios

### 1. Local Development

```bash
# Initialize project — prompts for location, template, and name
aegra init

cd <your-project>

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Install dependencies and start developing
uv sync
uv run aegra dev
```

### 2. Self-Hosted with Docker (Recommended for Production)

Best for: VPS, dedicated servers, on-premise infrastructure.

```bash
# Initialize project
aegra init
cd my-agent

# Configure production environment
cp .env.example .env
# Edit .env: set strong passwords, API keys, AUTH_TYPE, etc.

# Deploy
aegra up
```

The generated `docker-compose.yml` includes:
- PostgreSQL with pgvector for vector search
- Your app container built from `Dockerfile`
- Health checks on PostgreSQL
- Volume mounts for your graphs and config

To customize the deployment, edit `docker-compose.yml`:
- Add resource limits (`deploy.resources`)
- Add restart policies (`restart: unless-stopped`)
- Add a reverse proxy (nginx, traefik)

### 3. PaaS Deployment (Railway, Render, Fly.io)

Best for: Quick deployment without managing infrastructure.

**Setup:**
1. Create a PostgreSQL addon on your platform
2. Set `DATABASE_URL` environment variable (provided by the platform)
3. Set other env vars (`AUTH_TYPE`, `OPENAI_API_KEY`, etc.)

**Procfile / Start Command:**
```text
aegra serve --host 0.0.0.0 --port $PORT
```

Or in `Dockerfile`:
```dockerfile
CMD ["aegra", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

**Key differences from self-hosted:**
- No need for `docker-compose.yml` — the platform manages postgres
- Use `DATABASE_URL` instead of individual `POSTGRES_*` vars
- The platform handles scaling, TLS, and load balancing

### 4. Kubernetes

Best for: Large-scale, highly available deployments.

Use `aegra serve` as the container command:

```yaml
containers:
  - name: aegra
    image: your-registry/your-agent:latest
    command: ["aegra", "serve", "--host", "0.0.0.0", "--port", "8000"]
    env:
      - name: DATABASE_URL
        valueFrom:
          secretKeyRef:
            name: aegra-secrets
            key: database-url
    ports:
      - containerPort: 8000
    readinessProbe:
      httpGet:
        path: /health
        port: 8000
    livenessProbe:
      httpGet:
        path: /health
        port: 8000
```

PostgreSQL should be a managed service (CloudSQL, RDS, etc.) or a StatefulSet with persistent volumes.

## Environment Configuration

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` or `POSTGRES_*` | Database connection | `postgresql://user:pass@host:5432/db` |
| `AEGRA_CONFIG` | Path to aegra.json | `aegra.json` |

### Database Connection

You can configure the database connection in two ways:

**Option 1: Single connection string** (recommended for production/PaaS)
```env
DATABASE_URL=postgresql://user:password@host:5432/mydb
```

**Option 2: Individual fields** (used when DATABASE_URL is not set)
```env
POSTGRES_DB=mydb
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=secret
POSTGRES_PORT=5432
POSTGRES_USER=myuser
```

### Common Variables

```env
# Server
HOST=0.0.0.0
PORT=8000

# Auth
AUTH_TYPE=noop          # noop (no auth) or custom

# Logging
LOG_LEVEL=INFO
ENV_MODE=PRODUCTION     # LOCAL, DEVELOPMENT, PRODUCTION
```

See `.env.example` for the full list of available variables.

## Migrations

Migrations run **automatically on startup** for all deployment methods (`aegra dev`, `aegra serve`, `aegra up`). You do not need to run migrations manually.

## Health Checks

Aegra provides health check endpoints:

- `GET /health` — Health status
- `GET /ready` — Readiness check
- `GET /live` — Liveness check
- `GET /info` — Server info

Use these in Docker health checks, Kubernetes probes, or load balancer configurations.

## Troubleshooting

### "Connection refused" on startup

PostgreSQL is not reachable. Check:
- **Local dev?** → Use `aegra dev` (starts postgres automatically)
- **Docker?** → Use `aegra up` (starts postgres + app together)
- **External DB?** → Verify `DATABASE_URL` or `POSTGRES_*` in your `.env`
- **Missing `.env`?** → Copy `.env.example` to `.env` and configure it

### "Password authentication failed"

Wrong database credentials. Check that `POSTGRES_USER` and `POSTGRES_PASSWORD` in your `.env` match what PostgreSQL was initialized with.

### "Relation does not exist"

Migrations haven't been applied. This usually means the server couldn't connect to postgres during startup. Check the logs for connection errors, fix the connection, and restart.

### Migrations hang on startup

If you see "Running database migrations..." but nothing happens:
- Check if another process holds a lock on the database
- Check if the database is reachable but very slow
- Check the server logs for specific migration errors
