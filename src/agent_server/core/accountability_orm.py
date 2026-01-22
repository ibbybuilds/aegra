"""SQLAlchemy ORM models for Accountability Partner features."""

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .orm import Base


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("public.uuid_generate_v4()::text")
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional link to thread
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, server_default=text("'pending'")
    )  # pending, in_progress, completed, skipped
    due_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    priority: Mapped[str] = mapped_column(
        Text, server_default=text("'normal'")
    )  # critical, urgent, normal, low
    category: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # e.g. "Portfolio", "Learning"
    source_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_action_items_user", "user_id"),
        Index("idx_action_items_status", "status"),
        Index("idx_action_items_due", "due_date"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("public.uuid_generate_v4()::text")
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # e.g. "in_app", "email", "push"
    priority: Mapped[str] = mapped_column(Text, server_default=text("'normal'"))
    status: Mapped[str] = mapped_column(
        Text, server_default=text("'pending'")
    )  # pending, sent, read, failed
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),  # action_item_id, etc.
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_notifications_user_status", "user_id", "status"),
        Index("idx_notifications_scheduled", "scheduled_at"),
    )


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true")
    )
    preferences: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # e.g. { "email_frequency": "daily", "channels": ["in_app", "email"], "quiet_hours": ... }
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
