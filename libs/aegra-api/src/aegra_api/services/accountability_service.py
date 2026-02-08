"""Service for managing accountability items, notifications and user preferences.

Enhanced with:
- Richer notification queries (category, all statuses)
- Mark-all-read
- User preference management
- Activity tracking updates
- Notification dismissal
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.accountability_orm import (
    ActionItem,
    Notification,
    UserActivityTracking,
    UserPreferences,
)

logger = structlog.getLogger(__name__)


class AccountabilityService:
    """Service for managing accountability items and notifications."""

    # ------------------------------------------------------------------
    # Action Items
    # ------------------------------------------------------------------
    @staticmethod
    async def list_action_items(
        session: AsyncSession, user_id: str, statuses: list[str] | None = None
    ) -> Sequence[ActionItem]:
        if statuses is None:
            statuses = ["pending", "in_progress"]

        query = (
            select(ActionItem)
            .where(ActionItem.user_id == user_id, ActionItem.status.in_(statuses))
            .order_by(ActionItem.created_at.desc())
        )
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_action_item_status(
        session: AsyncSession, item_id: str, user_id: str, status: str
    ) -> dict:
        stmt = select(ActionItem).where(
            ActionItem.id == item_id, ActionItem.user_id == user_id
        )
        item = await session.scalar(stmt)

        if not item:
            raise ValueError("Item not found")

        if item.status == status:
            return {"status": "updated", "message": "no_change"}

        item.status = status
        item.updated_at = datetime.now(UTC)

        # Update activity tracking on completion
        if status == "completed":
            await AccountabilityService._record_action_completion(session, user_id)

        await session.commit()
        return {"status": "updated"}

    @staticmethod
    async def _record_action_completion(
        session: AsyncSession, user_id: str
    ) -> None:
        """Update activity tracking when an action item is completed."""
        result = await session.execute(
            select(UserActivityTracking).where(
                UserActivityTracking.user_id == user_id
            )
        )
        activity = result.scalar_one_or_none()
        if not activity:
            activity = UserActivityTracking(user_id=user_id)
            session.add(activity)

        now = datetime.now(UTC)
        activity.last_action_completed = now
        activity.updated_at = now

        # Update streak
        today = now.date()
        if activity.last_streak_date:
            delta = (today - activity.last_streak_date).days
            if delta == 1:
                activity.current_streak += 1
            elif delta > 1:
                activity.current_streak = 1
        else:
            activity.current_streak = 1

        activity.last_streak_date = today
        if activity.current_streak > activity.longest_streak:
            activity.longest_streak = activity.current_streak

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    @staticmethod
    async def list_notifications(
        session: AsyncSession,
        user_id: str,
        limit: int = 50,
        status: str | None = "pending",
        category: str | None = None,
    ) -> Sequence[Notification]:
        """List notifications with optional status and category filters."""
        filters = [Notification.user_id == user_id]

        if status:
            filters.append(Notification.status == status)

        if category and category != "all":
            filters.append(Notification.category == category)

        query = (
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def list_all_notifications(
        session: AsyncSession, user_id: str, limit: int = 50
    ) -> Sequence[Notification]:
        """Return both pending and read notifications (for notification center)."""
        query = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.status.in_(["pending", "read"]),
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def mark_notification_read(
        session: AsyncSession, notification_id: str, user_id: str
    ) -> dict:
        stmt = select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
        notification = await session.scalar(stmt)
        if not notification:
            raise ValueError("Notification not found")

        notification.status = "read"
        notification.read_at = datetime.now(UTC)
        await session.commit()
        return {"status": "updated"}

    @staticmethod
    async def mark_all_read(session: AsyncSession, user_id: str) -> dict:
        """Mark all pending notifications as read."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.status == "pending",
            )
            .values(status="read", read_at=now)
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"updated": result.rowcount}

    @staticmethod
    async def dismiss_notification(
        session: AsyncSession, notification_id: str, user_id: str
    ) -> dict:
        """Permanently dismiss a notification."""
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .values(status="dismissed")
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Notification not found")
        await session.commit()
        return {"status": "dismissed"}

    # ------------------------------------------------------------------
    # User Preferences
    # ------------------------------------------------------------------
    @staticmethod
    async def get_preferences(
        session: AsyncSession, user_id: str
    ) -> UserPreferences | None:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_preferences(
        session: AsyncSession, user_id: str, data: dict[str, Any]
    ) -> UserPreferences:
        """Create or update user notification preferences."""
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = UserPreferences(user_id=user_id)
            session.add(prefs)

        # Top-level fields
        if "notifications_enabled" in data:
            prefs.notifications_enabled = data["notifications_enabled"]
        if "location" in data:
            prefs.location = data["location"]
        if "push_subscription" in data:
            prefs.push_subscription = data["push_subscription"]

        # Merge into preferences JSONB
        pref_json = prefs.preferences or {}
        for key in (
            "max_daily",
            "digest_mode",
            "quiet_hours_start",
            "quiet_hours_end",
            "disabled_categories",
        ):
            if key in data:
                pref_json[key] = data[key]
        prefs.preferences = pref_json
        prefs.updated_at = datetime.now(UTC)

        await session.commit()
        return prefs

    # ------------------------------------------------------------------
    # Activity tracking
    # ------------------------------------------------------------------
    @staticmethod
    async def record_activity(
        session: AsyncSession, user_id: str, activity_type: str
    ) -> None:
        """Record a user activity (login, conversation, course, etc.)."""
        result = await session.execute(
            select(UserActivityTracking).where(
                UserActivityTracking.user_id == user_id
            )
        )
        activity = result.scalar_one_or_none()
        if not activity:
            activity = UserActivityTracking(user_id=user_id)
            session.add(activity)

        now = datetime.now(UTC)
        activity.updated_at = now

        if activity_type == "login":
            activity.last_login = now
        elif activity_type == "conversation":
            activity.last_conversation = now
        elif activity_type == "course":
            activity.last_course_activity = now

        await session.commit()

    @staticmethod
    async def get_activity(
        session: AsyncSession, user_id: str
    ) -> UserActivityTracking | None:
        result = await session.execute(
            select(UserActivityTracking).where(
                UserActivityTracking.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
