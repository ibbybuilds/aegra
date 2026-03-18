# =============================================================================
# Aegra Base Image
# =============================================================================
# Reusable base image containing only the Aegra core runtime + Alembic
# migrations. Does NOT include aegra.json or agent code — those are added
# by consumer projects via an overlay Dockerfile or volume mounts.
#
# Build:
#   docker build -f deployments/docker/Dockerfile -t aegra-base:0.8.2 .
#
# Use as overlay base:
#   FROM aegra-base:0.8.2
#   COPY aegra.json ./aegra.json
#   COPY src/ ./src/
# =============================================================================

ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim-bookworm AS base
ARG PY_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Create non-root user for runtime
RUN addgroup --system app && adduser --system --ingroup app app

# -----------------------------
# Builder stage
# -----------------------------
FROM base AS builder

# Retrieve the uv binary directly from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

# Install system build dependencies required for compiling Python extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy aegra-api package files and workspace lockfile
COPY libs/aegra-api/pyproject.toml libs/aegra-api/README.md ./
COPY uv.lock ./

# Install production dependencies only (no dev deps like langchain-openai, pytest, etc.).
RUN uv export --frozen --no-emit-project --no-dev --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

# Copy the actual project source code and forced includes (alembic).
COPY libs/aegra-api/src/ ./src/
COPY libs/aegra-api/alembic.ini ./alembic.ini
COPY libs/aegra-api/alembic/ ./alembic/

# Install the project package itself.
RUN uv pip install --system --compile-bytecode --no-deps .

# -----------------------------
# Final, minimal runtime image
# -----------------------------
FROM base AS final

LABEL org.opencontainers.image.title="aegra-base"
LABEL org.opencontainers.image.description="Aegra core runtime — self-hosted Agent Protocol server"
LABEL org.opencontainers.image.source="https://github.com/ibbybuilds/aegra"

# Install only minimal runtime libs (libpq5 needed by psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
COPY --from=builder /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy runtime assets required by alembic (migrations run on startup)
COPY libs/aegra-api/alembic.ini ./alembic.ini
COPY libs/aegra-api/alembic/ ./alembic/

EXPOSE 2026

# Run as non-root
USER app

# Default command - can be overridden by docker-compose
CMD ["aegra", "serve"]
