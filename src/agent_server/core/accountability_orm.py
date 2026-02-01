"""SQLAlchemy ORM models for Accountability Partner features."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    Index,
    Integer,
    Numeric,
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
    # Enhanced reminder fields
    advisor_persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_sent_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    last_reminder_sent: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
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
    category: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # deadline, opportunity, celebration, inactivity
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),  # action_item_id, etc.
    )
    action_buttons: Mapped[list | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
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
    # e.g. { "email_frequency": "daily", "channels": ["in_app", "push"], "quiet_hours": ... }
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    push_subscription: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class DiscoveredOpportunity(Base):
    """Opportunities discovered for users (events, jobs) matched to their enrolled courses."""

    __tablename__ = "discovered_opportunities"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default=text("public.uuid_generate_v4()::text")
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # 'event' or 'job'
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_score: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=3, scale=2), nullable=True
    )  # 0.00 - 1.00
    matched_track: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Track that triggered match
    status: Mapped[str] = mapped_column(
        Text, server_default=text("'new'")
    )  # new, notified, dismissed, applied, expired
    discovered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index("idx_opportunities_user", "user_id"),
        Index("idx_opportunities_status", "status"),
        Index("idx_opportunities_type", "opportunity_type"),
        Index("idx_opportunities_user_status", "user_id", "status"),
    )


class UserActivityTracking(Base):
    """Track user activity for inactivity detection and streak management."""

    __tablename__ = "user_activity_tracking"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_login: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_conversation: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_course_activity: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_action_completed: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    current_streak: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    last_streak_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    engagement_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), server_default=text("0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

