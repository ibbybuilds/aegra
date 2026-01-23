FROM python:3.11-slim-bookworm AS base

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
# This is the recommended installation method for Docker builds.
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv

# Install system build dependencies required for compiling Python extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files ONLY.
# We explicitly exclude README.md and src/ at this stage.
# This ensures that changes to documentation or source code do not invalidate
# the heavy dependency installation layer cached by Docker.
COPY pyproject.toml uv.lock ./

# Install dependencies strictly from uv.lock.
# 1. `uv export`: Converts uv.lock into a requirements.txt format with pinned versions.
#    - `--frozen`: Ensures the lockfile is in sync with pyproject.toml (fails otherwise).
#    - `--no-emit-project`: Excludes the current project from installation (we install it later).
# 2. `uv pip install`: Installs the dependencies into the system site-packages.
RUN uv export --frozen --no-dev --no-emit-project --format=requirements-txt > requirements.txt && \
    uv pip install --system --compile-bytecode -r requirements.txt && \
    rm requirements.txt

# Copy project metadata (README).
# This is copied in a separate layer after dependencies are installed.
# We need it for the final project installation (if referenced in pyproject.toml),
# but changing it should not trigger a re-download of PyPI packages.
COPY README.md ./

# Copy the actual project source code.
COPY src/ ./src/

# Install the project package itself.
# - `--no-deps`: Critical flag. Prevents uv from re-resolving or checking PyPI,
#   as all dependencies are already guaranteed to be installed in the previous layer.
# - `--compile-bytecode`: Optimizes startup time by pre-compiling .pyc files.
RUN uv pip install --system --compile-bytecode --no-deps .

# -----------------------------
# Final, minimal runtime image
# -----------------------------
FROM base AS final

# Install only minimal runtime libs (psycopg[binary] used, so libpq not required at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy runtime assets required by the app and alembic
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY aegra.json ./aegra.json
COPY auth.py ./auth.py
COPY graphs/ ./graphs/

# Copy src to keep compatibility with current compose command using 'src.agent_server.main:app'
# (We can switch compose to 'agent_server.main:app' later and drop this for a smaller image.)
COPY src/ ./src/

EXPOSE 8000

# Run as non-root
USER app

# Leave default CMD empty so docker-compose command can run migrations then start uvicorn
# CMD ["uvicorn", "src.agent_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
