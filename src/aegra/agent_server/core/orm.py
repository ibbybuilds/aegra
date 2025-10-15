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
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()


class Assistant(Base):
    __tablename__ = "assistant"

    # TEXT PK with DB-side generation using uuid_generate_v4()::text
    assistant_id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("uuid_generate_v4()::text")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    metadata_dict: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), name="metadata"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

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
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    metadata_dict: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), name="metadata"
    )
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Thread(Base):
    __tablename__ = "thread"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, server_default=text("'idle'"))
    # Database column is 'metadata_json' (per database.py). ORM attribute 'metadata_json' must map to that column.
    metadata_json: Mapped[dict] = mapped_column(
        "metadata_json", JSONB, server_default=text("'{}'::jsonb")
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Indexes for performance
    __table_args__ = (Index("idx_thread_user", "user_id"),)


class Run(Base):
    __tablename__ = "runs"

    # TEXT PK with DB-side generation using uuid_generate_v4()::text
    run_id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("uuid_generate_v4()::text")
    )
    thread_id: Mapped[str] = mapped_column(
        Text, ForeignKey("thread.thread_id", ondelete="CASCADE"), nullable=False
    )
    assistant_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("assistant.assistant_id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    input: Mapped[dict | None] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    # Some environments may not yet have a 'config' column; make it nullable without default to match existing DB.
    # If migrations add this column later, it's already represented here.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

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
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_run_events_run_id", "run_id"),
        Index("idx_run_events_seq", "run_id", "seq"),
    )


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return a cached async_sessionmaker bound to db_manager.engine."""
    global async_session_maker
    if async_session_maker is None:
        from .database import db_manager

        engine = db_manager.get_engine()
        async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    return async_session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession."""
    maker = _get_session_maker()
    async with maker() as session:
        yield session
