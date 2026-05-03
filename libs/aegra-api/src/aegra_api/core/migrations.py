"""Database migration utilities for Aegra.

Provides automatic Alembic migration support for both development (repo)
and production (pip install) deployments. Resolves the alembic.ini and
migration scripts from either CWD or the installed aegra-api package.

Two entry points:

- ``run_migrations()`` always upgrades to head, acquiring the alembic
  advisory lock unconditionally. Suitable for explicit, out-of-band
  invocation (init containers, Helm pre-upgrade Jobs, ``aegra db upgrade``).

- ``run_migrations_if_needed()`` first does a cheap read-only check
  comparing the database's current revision against the migration
  script head. If they match, it returns without acquiring any lock.
  This is what the FastAPI startup path uses to keep multi-pod boots
  fast in the steady state, where the database is already migrated.
"""

import asyncio
from pathlib import Path

import psycopg
import structlog
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from aegra_api.settings import settings
from alembic import command

logger = structlog.get_logger(__name__)


def find_alembic_ini() -> Path:
    """Find alembic.ini file.

    Resolution order:
    1. alembic.ini in CWD (repo development, Docker)
    2. Bundled with aegra_api package (pip install)

    Returns:
        Absolute path to alembic.ini

    Raises:
        FileNotFoundError: If alembic.ini cannot be found
    """
    # 1. CWD (works in repo dev and Docker)
    cwd_ini = Path("alembic.ini")
    if cwd_ini.exists():
        return cwd_ini.resolve()

    # 2. Package bundled (pip install aegra-api)
    # In installed package: site-packages/aegra_api/alembic.ini
    package_dir = Path(__file__).resolve().parent.parent  # aegra_api/
    package_ini = package_dir / "alembic.ini"
    if package_ini.exists():
        return package_ini

    # 3. Development layout (src layout: libs/aegra-api/src/aegra_api/ → libs/aegra-api/)
    dev_root = package_dir.parent.parent  # Up from src/aegra_api/ to libs/aegra-api/
    dev_ini = dev_root / "alembic.ini"
    if dev_ini.exists():
        return dev_ini

    raise FileNotFoundError(
        "Could not find alembic.ini. Ensure aegra-api is properly installed or run from the project root."
    )


def get_alembic_config() -> Config:
    """Create Alembic Config with correct paths.

    Works in both development (repo) and production (pip install) environments.
    Resolves relative script_location to absolute path so migrations work
    regardless of CWD.

    Returns:
        Configured Alembic Config object
    """
    ini_path = find_alembic_ini()
    cfg = Config(str(ini_path))

    # Resolve script_location to absolute path so it works from any CWD
    script_location = cfg.get_main_option("script_location")
    if script_location and not Path(script_location).is_absolute():
        abs_script_location = str((ini_path.parent / script_location).resolve())
        cfg.set_main_option("script_location", abs_script_location)

    return cfg


def _is_database_up_to_date(cfg: Config) -> bool:
    """Check whether the database is already at the migration head.

    Reads ``alembic_version`` via a short-lived sync engine and compares
    against the script directory's head revision. No advisory lock is
    acquired, so this is safe to call from many pods concurrently.

    Returns:
        True if there is nothing to apply (the database revision matches
        head, or the script directory has no revisions at all), False
        otherwise (migration pending, or no current revision yet).
    """
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()

    # Empty script directory: nothing to apply, skip the upgrade entirely.
    if head is None:
        return True

    # Open a short-lived psycopg connection directly using the libpq-style
    # URL from settings. This deliberately bypasses SQLAlchemy's URL parser
    # so multi-host DATABASE_URL values (``postgresql://h1,h2/db``, see
    # ``DatabaseSettings._to_sqlalchemy_multihost``) work natively via libpq
    # failover. We do not reuse the app's async pool because this runs
    # before pools initialize, and we want the connection closed before
    # alembic opens its own.
    with psycopg.connect(settings.db.database_url_sync) as conn:
        ctx = MigrationContext.configure(conn)
        current = ctx.get_current_revision()

    return current == head


def run_migrations() -> None:
    """Unconditionally run all pending database migrations.

    Acquires Alembic's advisory lock and upgrades to head. Use this for
    explicit invocations: init containers, Helm pre-upgrade Jobs, or the
    ``aegra db upgrade`` CLI command.
    """
    cfg = get_alembic_config()
    logger.info("running database migrations")
    command.upgrade(cfg, "head")
    logger.info("database migrations completed")


def run_migrations_if_needed() -> None:
    """Run migrations only when the database is behind head.

    Performs a lock-free read of the current revision first. If it
    already matches head, returns immediately without entering the
    alembic upgrade path. Otherwise falls through to ``run_migrations``.

    This keeps app pod boots cheap in the steady state where the database
    is already at head, avoiding the advisory-lock contention that
    serializes ``alembic upgrade head`` calls across replicas.
    """
    cfg = get_alembic_config()
    try:
        if _is_database_up_to_date(cfg):
            logger.debug("database already at migration head; skipping upgrade")
            return
    except Exception as exc:
        # Fall through to full upgrade so first-time installs (where
        # alembic_version doesn't exist yet) still work. The full path
        # logs and raises on real failures.
        logger.debug("revision precheck failed; falling back to full upgrade", error=str(exc))

    logger.info("running database migrations")
    command.upgrade(cfg, "head")
    logger.info("database migrations completed")


async def run_migrations_async() -> None:
    """Run pending migrations from an async context (lock-free fast path).

    Wraps :func:`run_migrations_if_needed` in a thread executor because
    Alembic's env.py uses ``asyncio.run()`` internally, which requires
    its own event loop.
    """
    await asyncio.to_thread(run_migrations_if_needed)
