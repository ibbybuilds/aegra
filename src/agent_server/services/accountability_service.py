"""Service for managing accountability items and notifications."""

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.accountability_orm import ActionItem, Notification

logger = structlog.getLogger(__name__)


class AccountabilityService:
    """Service for managing accountability items and notifications."""

    @staticmethod
    async def list_action_items(
        session: AsyncSession, user_id: str, statuses: list[str] | None = None
    ) -> Sequence[ActionItem]:
        """List active action items for a user.

        Args:
            session: Database session
            user_id: User ID
            statuses: List of statuses to filter by

        Returns:
            List of ActionItem ORM objects
        """
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
        """Update the status of an action item.

        Args:
            session: Database session
            item_id: Action Item ID
            user_id: User ID (for authorization)
            status: New status

        Returns:
            Dict with update status

        Raises:
            ValueError: If item not found
        """
        stmt = select(ActionItem).where(
            ActionItem.id == item_id, ActionItem.user_id == user_id
        )
        item = await session.scalar(stmt)

        if not item:
            raise ValueError("Item not found")

        # Idempotency check
        if item.status == status:
            return {"status": "updated", "message": "no_change"}

        item.status = status
        await session.commit()
        return {"status": "updated"}

    @staticmethod
    async def list_notifications(
        session: AsyncSession, user_id: str, limit: int = 50, status: str = "pending"
    ) -> Sequence[Notification]:
        """List notifications for a user.

        Args:
            session: Database session
            user_id: User ID
            limit: Max number of notifications
            status: Filter by status

        Returns:
            List of Notification ORM objects
        """
        query = (
            select(Notification)
            .where(Notification.user_id == user_id, Notification.status == status)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def mark_notification_read(
        session: AsyncSession, notification_id: str, user_id: str
    ) -> dict:
        """Mark a notification as read.

        Args:
            session: Database session
            notification_id: Notification ID
            user_id: User ID

        Returns:
            Dict with update status

        Raises:
            ValueError: If notification not found
        """
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
