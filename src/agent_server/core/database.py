"""Database manager with LangGraph integration"""

import os

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..config import load_store_config

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages database connections and LangGraph persistence components"""

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None

        # Shared pool for LangGraph components (Checkpointer + Store)
        self.lg_pool: AsyncConnectionPool | None = None

        self._checkpointer: AsyncPostgresSaver | None = None
        self._store: AsyncPostgresStore | None = None

        self._database_url = os.getenv(
            "DATABASE_URL",
            (
                f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
            ),
        )

    async def initialize(self) -> None:
        """Initialize database connections and LangGraph components"""
        # Idempotency check: if already initialized, do nothing
        if self.engine:
            return

        # 1. SQLAlchemy Engine (app metadata, uses asyncpg)
        # We strictly limit this pool because the main load
        # is handled by LangGraph components.
        self.engine = create_async_engine(
            self._database_url,
            pool_size=int(os.getenv("SA_POOL_SIZE", "2")),
            max_overflow=int(os.getenv("SA_MAX_OVERFLOW", "0")),
            pool_pre_ping=True,
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
        )

        # 2. Shared Pool for LangGraph (uses psycopg)
        # Convert SQLAlchemy URL (asyncpg) to psycopg format
        dsn_for_lg = self._database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )

        lg_min = int(os.getenv("LG_MIN_POOL_SIZE", "1"))
        lg_max = int(os.getenv("LG_POOL_SIZE", "6"))

        lg_kwargs = {
            "autocommit": True,
            "prepare_threshold": 0,  # Optimization for PgBouncer/Kubernetes compatibility
            "row_factory": dict_row,  # LangGraph requires dictionary rows, not tuples
        }

        # Create a single shared pool.
        # 'open=False' is important to avoid RuntimeWarning; we open it explicitly below.
        self.lg_pool = AsyncConnectionPool(
            conninfo=dsn_for_lg,
            min_size=lg_min,
            max_size=lg_max,
            open=False,
            kwargs=lg_kwargs,
            check=AsyncConnectionPool.check_connection,
        )

        # Explicitly open the pool
        await self.lg_pool.open()

        # 3. Initialize LangGraph components using the shared pool
        # Passing 'conn=self.lg_pool' prevents components from creating their own pools.

        logger.info(
            f"Initializing LangGraph components with shared pool (max {lg_max} conns)..."
        )

        self._checkpointer = AsyncPostgresSaver(conn=self.lg_pool)
        await self._checkpointer.setup()  # Ensure tables exist

        # Load store configuration for semantic search (if configured)
        store_config = load_store_config()
        index_config = store_config.get("index") if store_config else None

        self._store = AsyncPostgresStore(conn=self.lg_pool, index=index_config)
        await self._store.setup()  # Ensure tables exist

        if index_config:
            embed_model = index_config.get("embed", "unknown")
            logger.info(f"Semantic store enabled with embeddings: {embed_model}")

        logger.info("✅ Database and LangGraph components initialized")

    async def close(self) -> None:
        """Close database connections"""
        # Close SQLAlchemy engine
        if self.engine:
            await self.engine.dispose()
            self.engine = None

        # Close shared LangGraph pool
        if self.lg_pool:
            await self.lg_pool.close()
            self.lg_pool = None
            self._checkpointer = None
            self._store = None

        logger.info("✅ Database connections closed")

    def get_checkpointer(self) -> AsyncPostgresSaver:
        """Return the live AsyncPostgresSaver instance."""
        if self._checkpointer is None:
            raise RuntimeError("Database not initialized")
        return self._checkpointer

    def get_store(self) -> AsyncPostgresStore:
        """Return the live AsyncPostgresStore instance."""
        if self._store is None:
            raise RuntimeError("Database not initialized")
        return self._store

    def get_engine(self) -> AsyncEngine:
        """Get the SQLAlchemy engine for metadata tables"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        return self.engine


# Global database manager instance
db_manager = DatabaseManager()
