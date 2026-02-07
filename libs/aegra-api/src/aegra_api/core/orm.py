"""SQLAlchemy ORM setup for persistent assistant/thread/run records.

This module creates:
• `Base` – the declarative base used by our models.
• `Assistant`, `Thread`, `Run` – ORM models mirroring the bootstrap tables
  already created in ``DatabaseManager._create_metadata_tables``.
• `async_session_maker` – a factory that hands out `AsyncSession` objects
  bound to the shared engine managed by `db_manager`.
• `get_session` – FastAPI dependency helper for routers.

Nothing is auto-imported by FastAPI yet; routers will `from ...core.db import get_session`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Assistant(Base):
    __tablename__ = "assistant"

    # TEXT PK with DB-side generation using uuid_generate_v4()::text
    assistant_id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("public.uuid_generate_v4()::text")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    metadata_dict: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), name="metadata")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    # Indexes for performance
    __table_args__ = (
        Index("idx_assistant_user", "user_id"),
        Index("idx_assistant_user_assistant", "user_id", "assistant_id", unique=True),
        Index(
            "idx_assistant_user_graph_config",
            "user_id",
            "graph_id",
            "config",
            unique=True,
        ),
    )


class AssistantVersion(Base):
    __tablename__ = "assistant_versions"

    assistant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("assistant.assistant_id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    metadata_dict: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), name="metadata")
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Thread(Base):
    __tablename__ = "thread"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, server_default=text("'idle'"))
    # Database column is 'metadata_json' (per database.py). ORM attribute 'metadata_json' must map to that column.
    metadata_json: Mapped[dict] = mapped_column("metadata_json", JSONB, server_default=text("'{}'::jsonb"))
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    # Indexes for performance
    __table_args__ = (Index("idx_thread_user", "user_id"),)


class Run(Base):
    __tablename__ = "runs"

    # TEXT PK with DB-side generation using uuid_generate_v4()::text
    run_id: Mapped[str] = mapped_column(Text, primary_key=True, server_default=text("public.uuid_generate_v4()::text"))
    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("thread.thread_id", ondelete="CASCADE"), nullable=False)
    assistant_id: Mapped[str | None] = mapped_column(Text, ForeignKey("assistant.assistant_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    input: Mapped[dict | None] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Some environments may not yet have a 'config' column; make it nullable without default to match existing DB.
    # If migrations add this column later, it's already represented here.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    # Indexes for performance
    __table_args__ = (
        Index("idx_runs_thread_id", "thread_id"),
        Index("idx_runs_user", "user_id"),
        Index("idx_runs_status", "status"),
        Index("idx_runs_assistant_id", "assistant_id"),
        Index("idx_runs_created_at", "created_at"),
    )


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    # Indexes for performance
    __table_args__ = (
        Index("idx_run_events_run_id", "run_id"),
        Index("idx_run_events_seq", "run_id", "seq"),
    )


class ActivityLog(Base):
    """Activity log for tracking student/user interactions with the AI system"""

    __tablename__ = "activity_log"

    activity_id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("uuid_generate_v4()::text")
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # e.g., "prompt", "query", "run_started", "run_completed", "run_failed"
    action_status: Mapped[str] = mapped_column(
        Text, server_default=text("'success'")
    )  # "success", "failed", "interrupted"
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    metadata_json: Mapped[dict] = mapped_column(
        "metadata_json", JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Indexes for performance and common queries
    __table_args__ = (
        Index("idx_activity_log_user", "user_id"),
        Index("idx_activity_log_user_created", "user_id", "created_at"),
        Index("idx_activity_log_assistant", "assistant_id"),
        Index("idx_activity_log_thread", "thread_id"),
        Index("idx_activity_log_action_type", "action_type"),
        Index("idx_activity_log_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return a cached async_sessionmaker bound to db_manager.engine."""
    global async_session_maker
    if async_session_maker is None:
        from aegra_api.core.database import db_manager

        # Ensure database is initialized before getting engine
        if not db_manager.engine:
            raise RuntimeError(
                "Database not initialized. Call db_manager.initialize() during app startup."
            )
        async_session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
    return async_session_maker


def initialize_session_maker() -> None:
    """Initialize the session maker during app startup."""
    _get_session_maker()


def reset_session_maker() -> None:
    """Reset the session maker cache on shutdown."""
    global async_session_maker
    async_session_maker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession."""
    maker = _get_session_maker()
    async with maker() as session:
        yield session
