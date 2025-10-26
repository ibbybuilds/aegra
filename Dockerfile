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
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and source
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

# Install project (builds wheel and installs dependencies specified in pyproject)
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir .

# -----------------------------
# Final, minimal runtime image
# -----------------------------
FROM base AS final

# Install only minimal runtime libs (psycopg[binary] used, so libpq not required at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages and console scripts from builder
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


