"""Service for managing activity logs and analytics"""

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import ActivityLog as ActivityLogORM
from aegra_api.models.activity_logs import ActivityLog

logger = structlog.getLogger(__name__)


class ActivityService:
    """Service for logging and retrieving student activity"""

    @staticmethod
    async def log_activity(
        session: AsyncSession,
        user_id: str,
        action_type: str,
        assistant_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        action_status: str = "success",
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log a user activity to the database

        Args:
            session: Database session
            user_id: ID of the user performing the action
            action_type: Type of action (e.g., 'prompt', 'query', 'run_started')
            assistant_id: Associated assistant ID
            thread_id: Associated thread ID
            run_id: Associated run ID
            action_status: Status of the action ('success', 'failed', 'interrupted')
            details: Additional details about the action
            metadata: Metadata for the action

        Returns:
            ActivityLog model with the created activity
        """
        activity = ActivityLogORM(
            user_id=user_id,
            action_type=action_type,
            assistant_id=assistant_id,
            thread_id=thread_id,
            run_id=run_id,
            action_status=action_status,
            details=details or {},
            metadata=metadata or {},
        )
        session.add(activity)
        await session.flush()

        logger.info(
            "Activity logged",
            action_type=action_type,
            user_id=user_id,
            activity_id=activity.activity_id,
        )

        return ActivityLog.model_validate(activity)

    @staticmethod
    async def get_user_activity_logs(
        session: AsyncSession,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        action_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[ActivityLog], int]:
        """Retrieve activity logs for a specific user

        Args:
            session: Database session
            user_id: User ID to filter by
            limit: Maximum number of results
            offset: Results offset for pagination
            action_type: Optional filter by action type
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Tuple of (list of ActivityLog models, total count)
        """
        query = select(ActivityLogORM).where(ActivityLogORM.user_id == user_id)

        if action_type:
            query = query.where(ActivityLogORM.action_type == action_type)

        if start_date:
            query = query.where(ActivityLogORM.created_at >= start_date)

        if end_date:
            query = query.where(ActivityLogORM.created_at <= end_date)

        # Get total count
        count_query = select(func.count(ActivityLogORM.activity_id)).where(
            ActivityLogORM.user_id == user_id
        )

        if action_type:
            count_query = count_query.where(ActivityLogORM.action_type == action_type)
        if start_date:
            count_query = count_query.where(ActivityLogORM.created_at >= start_date)
        if end_date:
            count_query = count_query.where(ActivityLogORM.created_at <= end_date)

        total = await session.scalar(count_query)

        # Get paginated results
        query = (
            query.order_by(desc(ActivityLogORM.created_at)).limit(limit).offset(offset)
        )
        activities = await session.scalars(query)

        return (
            [ActivityLog.model_validate(a) for a in activities],
            total or 0,
        )

    @staticmethod
    async def get_activity_logs(
        session: AsyncSession,
        user_id: str | None = None,
        assistant_id: str | None = None,
        action_type: str | None = None,
        action_status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityLog], int]:
        """Retrieve activity logs with multiple filters

        Args:
            session: Database session
            user_id: Optional filter by user ID
            assistant_id: Optional filter by assistant ID
            action_type: Optional filter by action type
            action_status: Optional filter by action status
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of results
            offset: Results offset

        Returns:
            Tuple of (list of ActivityLog models, total count)
        """
        conditions = []

        if user_id:
            conditions.append(ActivityLogORM.user_id == user_id)
        if assistant_id:
            conditions.append(ActivityLogORM.assistant_id == assistant_id)
        if action_type:
            conditions.append(ActivityLogORM.action_type == action_type)
        if action_status:
            conditions.append(ActivityLogORM.action_status == action_status)
        if start_date:
            conditions.append(ActivityLogORM.created_at >= start_date)
        if end_date:
            conditions.append(ActivityLogORM.created_at <= end_date)

        query = select(ActivityLogORM)
        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count(ActivityLogORM.activity_id))
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total = await session.scalar(count_query)

        # Get paginated results
        query = (
            query.order_by(desc(ActivityLogORM.created_at)).limit(limit).offset(offset)
        )
        activities = await session.scalars(query)

        return (
            [ActivityLog.model_validate(a) for a in activities],
            total or 0,
        )

    @staticmethod
    async def get_user_activity_summary(
        session: AsyncSession,
        user_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get activity summary statistics for a user

        Args:
            session: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary containing activity summary
        """
        query = select(ActivityLogORM).where(ActivityLogORM.user_id == user_id)

        if start_date:
            query = query.where(ActivityLogORM.created_at >= start_date)
        if end_date:
            query = query.where(ActivityLogORM.created_at <= end_date)

        activities = await session.scalars(query)
        activities_list = list(activities)

        # Calculate statistics
        action_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        assistant_counts: dict[str, int] = {}

        for activity in activities_list:
            # Count by action type
            action_counts[activity.action_type] = (
                action_counts.get(activity.action_type, 0) + 1
            )

            # Count by status
            status_counts[activity.action_status] = (
                status_counts.get(activity.action_status, 0) + 1
            )

            # Count by assistant
            if activity.assistant_id:
                assistant_counts[activity.assistant_id] = (
                    assistant_counts.get(activity.assistant_id, 0) + 1
                )

        return {
            "total_activities": len(activities_list),
            "action_counts": action_counts,
            "status_counts": status_counts,
            "assistant_counts": assistant_counts,
        }
