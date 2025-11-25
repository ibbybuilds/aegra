"""Database manager with LangGraph integration"""

import os
from typing import Any

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages database connections and LangGraph persistence components"""

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._checkpointer_cm: Any = None  # holds the contextmanager so we can close it
        self._store: AsyncPostgresStore | None = None
        self._store_cm: Any = None
        self._database_url = os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/aegra"
        )

    async def initialize(self) -> None:
        """Initialize database connections and LangGraph components"""
        # Check if this is a Neon (or other cloud) PostgreSQL that requires SSL
        is_cloud_postgres = (
            "neon.tech" in self._database_url or "supabase" in self._database_url
        )

        # SQLAlchemy for our minimal Agent Protocol metadata tables
        # Using pool_pre_ping=True to handle stale/reset connections (important for Neon serverless)
        # For asyncpg, SSL is enabled via connect_args, not URL parameter
        connect_args = {"ssl": True} if is_cloud_postgres else {}

        self.engine = create_async_engine(
            self._database_url,
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
            pool_pre_ping=True,  # Check connection health before use
            pool_size=5,  # Conservative pool size for serverless
            max_overflow=10,  # Allow extra connections under load
            pool_recycle=300,  # Recycle connections every 5 minutes
            connect_args=connect_args,
        )

        # Convert asyncpg URL to psycopg format for LangGraph
        # LangGraph packages require psycopg format, not asyncpg
        dsn = self._database_url.replace("postgresql+asyncpg://", "postgresql://")

        # For psycopg (LangGraph), add sslmode=require for cloud PostgreSQL
        if is_cloud_postgres:
            if "?" in dsn:
                dsn += "&sslmode=require"
            else:
                dsn += "?sslmode=require"

        # Store connection string for creating LangGraph components on demand
        self._langgraph_dsn = dsn
        self.checkpointer = None
        self.store = None
        # Note: LangGraph components will be created as context managers when needed

        # Note: Database schema is now managed by Alembic migrations
        # Run 'alembic upgrade head' to apply migrations

        logger.info("✅ Database and LangGraph components initialized")

    async def close(self) -> None:
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

        # Close the cached checkpointer if we opened one
        if self._checkpointer_cm is not None:
            await self._checkpointer_cm.__aexit__(None, None, None)
            self._checkpointer_cm = None
            self._checkpointer = None

        if self._store_cm is not None:
            await self._store_cm.__aexit__(None, None, None)
            self._store_cm = None
            self._store = None

        logger.info("✅ Database connections closed")

    async def get_checkpointer(self) -> AsyncPostgresSaver:
        """Return a live AsyncPostgresSaver.

        We enter the async context manager once and cache the saver so that
        subsequent calls reuse the same database connection pool.  LangGraph
        expects the *real* saver object (it calls methods like
        ``get_next_version``), so returning the context manager wrapper would
        fail.
        """
        if not hasattr(self, "_langgraph_dsn"):
            raise RuntimeError("Database not initialized")
        if self._checkpointer is None:
            self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(
                self._langgraph_dsn
            )
            self._checkpointer = await self._checkpointer_cm.__aenter__()
            # Ensure required tables exist (idempotent)
            await self._checkpointer.setup()
        return self._checkpointer

    async def get_store(self) -> AsyncPostgresStore:
        """Return a live AsyncPostgresStore instance (vector + KV)."""
        if not hasattr(self, "_langgraph_dsn"):
            raise RuntimeError("Database not initialized")
        if self._store is None:
            self._store_cm = AsyncPostgresStore.from_conn_string(self._langgraph_dsn)
            self._store = await self._store_cm.__aenter__()
            # ensure schema
            await self._store.setup()
        return self._store

    def get_engine(self) -> AsyncEngine:
        """Get the SQLAlchemy engine for metadata tables"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        return self.engine


# Global database manager instance
db_manager = DatabaseManager()
