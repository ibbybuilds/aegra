#!/usr/bin/env bash
set -euo pipefail

# Best-effort: attempt to run alembic migrations if alembic is available.
# This will not stop the container from starting if migrations fail (we log and continue).
if command -v alembic >/dev/null 2>&1; then
  echo "[entrypoint] Running alembic upgrade head..."
  alembic upgrade head || {
    echo "[entrypoint] Alembic migration failed, continuing startup" >&2
  }
else
  echo "[entrypoint] alembic not found, skipping migrations"
fi

echo "[entrypoint] Starting application: $@"

# If the command is uvicorn and no --port argument was provided, append --port from $PORT (if set), defaulting to 8000.
if [ "${1:-}" = "uvicorn" ]; then
  # check if any arg equals --port
  if ! printf '%s\n' "$@" | grep -q -- '--port'; then
    set -- "$@" --port "${PORT:-8000}"
  fi
fi

exec "$@"
