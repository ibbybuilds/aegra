"""Enhanced Scheduler service for the Accountability Partner system.

Features:
- Tiered deadline reminders (24h, 2h, overdue)
- Inactivity detection (3 days, 7 days)
- Cleanup of old notifications
- Opportunity expiration
"""

from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent_server.core.accountability_orm import (
    ActionItem,
    DiscoveredOpportunity,
    Notification,
    UserActivityTracking,
)
from agent_server.core.database import db_manager

logger = structlog.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            # Deadline reminder job (every 15 minutes)
            self.scheduler.add_job(
                self.check_deadlines,
                IntervalTrigger(minutes=15),
                id="check_deadlines",
                replace_existing=True,
            )

            # Inactivity check job (every 6 hours)
            self.scheduler.add_job(
                self.check_inactivity,
                IntervalTrigger(hours=6),
                id="check_inactivity",
                replace_existing=True,
            )

            # Cleanup job (runs daily)
            self.scheduler.add_job(
                self.check_cleanup,
                IntervalTrigger(hours=24),
                id="check_cleanup",
                replace_existing=True,
            )

            # Opportunity expiration job (runs hourly)
            self.scheduler.add_job(
                self.expire_opportunities,
                IntervalTrigger(hours=1),
                id="expire_opportunities",
                replace_existing=True,
            )

            self.scheduler.start()
            logger.info("Scheduler service started with enhanced accountability jobs")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler service stopped")

    async def check_cleanup(self) -> None:
        """Cleanup old notifications to maintain database health."""
        logger.debug("Running notification cleanup")
        try:
            if not db_manager.engine:
                logger.debug("Database not available, skipping cleanup")
                return

            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                cutoff_read = now - timedelta(days=7)  # Keep read notifications for 7 days
                cutoff_old = now - timedelta(days=30)  # Keep unread notifications for 30 days

                stmt = delete(Notification).where(
                    or_(
                        and_(
                            Notification.status == "read",
                            Notification.created_at < cutoff_read,
                        ),
                        Notification.created_at < cutoff_old,
                    )
                )

                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info("Cleanup completed", deleted_count=result.rowcount)

                await session.commit()
        except Exception as e:
            logger.error("Error in check_cleanup", error=str(e), exc_info=True)

    async def check_deadlines(self) -> None:
        """Check for upcoming deadlines and generate tiered notifications.

        Tiers:
        - 24 hours before: Friendly reminder
        - 2 hours before: Urgent reminder
        - Overdue: Overdue alert
        """
        logger.debug("Checking deadlines")
        try:
            if not db_manager.engine:
                logger.debug("Database not available, skipping deadline check")
                return

            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                two_hours_from_now = now + timedelta(hours=2)
                twenty_four_hours_from_now = now + timedelta(hours=24)

                # Get all pending action items with due dates
                result = await session.execute(
                    select(ActionItem).where(
                        and_(
                            ActionItem.status == "pending",
                            ActionItem.due_date.isnot(None),
                        )
                    )
                )
                items = result.scalars().all()

                for item in items:
                    due_date = item.due_date
                    if not due_date:
                        continue

                    # Determine reminder tier
                    reminder_tier = None
                    priority = "normal"
                    title = ""
                    content = ""

                    if due_date < now:
                        # Overdue
                        reminder_tier = "overdue"
                        priority = "critical"
                        title = "⚠️ Action Item Overdue"
                        content = f"Your task is overdue: {item.description}"
                    elif due_date <= two_hours_from_now:
                        # 2 hours warning
                        reminder_tier = "2h"
                        priority = "high"
                        title = "⏰ Task Due in 2 Hours"
                        content = f"Almost time! {item.description}"
                    elif due_date <= twenty_four_hours_from_now:
                        # 24 hours warning
                        reminder_tier = "24h"
                        priority = "normal"
                        title = "📅 Task Due Tomorrow"
                        content = f"Friendly reminder: {item.description}"

                    if not reminder_tier:
                        continue

                    # Check if we should send (based on reminder_sent_count and last_reminder_sent)
                    should_send = await self._should_send_reminder(
                        item, reminder_tier, now
                    )

                    if should_send:
                        # Create notification
                        new_notif = Notification(
                            user_id=item.user_id,
                            title=title,
                            content=content,
                            channel="in_app",
                            priority=priority,
                            category="deadline",
                            status="pending",
                            metadata_json={
                                "action_item_id": item.id,
                                "reminder_tier": reminder_tier,
                            },
                            action_buttons=[
                                {"action": "complete", "title": "Mark Complete"},
                                {"action": "snooze", "title": "Snooze 1hr"},
                            ],
                        )
                        session.add(new_notif)

                        # Update item's reminder tracking
                        item.reminder_sent_count += 1
                        item.last_reminder_sent = now

                        logger.info(
                            "Sent deadline reminder",
                            action_item_id=item.id,
                            tier=reminder_tier,
                            reminder_count=item.reminder_sent_count,
                        )

                await session.commit()

        except Exception as e:
            logger.error("Error in check_deadlines", error=str(e), exc_info=True)

    async def _should_send_reminder(
        self, item: ActionItem, tier: str, now: datetime
    ) -> bool:
        """Determine if a reminder should be sent based on tier and timing."""
        # If never sent a reminder, always send
        if item.reminder_sent_count == 0:
            return True

        # If last reminder was recent (within 2 hours), skip
        if item.last_reminder_sent:
            hours_since_last = (now - item.last_reminder_sent).total_seconds() / 3600
            if hours_since_last < 2:
                return False

        # For overdue, limit to 3 reminders
        if tier == "overdue" and item.reminder_sent_count >= 3:
            return False

        return True

    async def check_inactivity(self) -> None:
        """Check for inactive users and generate check-in notifications.

        Tiers:
        - 3 days inactive: Friendly check-in
        - 7 days inactive: Re-engagement prompt
        """
        logger.debug("Checking for inactive users")
        try:
            if not db_manager.engine:
                logger.debug("Database not available, skipping inactivity check")
                return

            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                three_days_ago = now - timedelta(days=3)
                seven_days_ago = now - timedelta(days=7)

                # Find inactive users
                result = await session.execute(
                    select(UserActivityTracking).where(
                        or_(
                            UserActivityTracking.last_login < three_days_ago,
                            UserActivityTracking.last_conversation < three_days_ago,
                        )
                    )
                )
                inactive_users = result.scalars().all()

                for activity in inactive_users:
                    last_activity = max(
                        filter(
                            None,
                            [
                                activity.last_login,
                                activity.last_conversation,
                                activity.last_course_activity,
                            ],
                        ),
                        default=None,
                    )

                    if not last_activity:
                        continue

                    days_inactive = (now - last_activity).days

                    # Determine notification content
                    if days_inactive >= 7:
                        title = "👋 We miss you!"
                        content = "It's been a week since we last saw you. Your learning goals are waiting for you!"
                        priority = "high"
                    elif days_inactive >= 3:
                        title = "👋 Quick check-in"
                        content = "Haven't seen you in a few days. Ready to continue your learning journey?"
                        priority = "normal"
                    else:
                        continue

                    # Check for existing recent inactivity notification
                    exists_result = await session.execute(
                        select(Notification).where(
                            and_(
                                Notification.user_id == activity.user_id,
                                Notification.category == "inactivity",
                                Notification.created_at > (now - timedelta(days=3)),
                            )
                        )
                    )

                    if exists_result.scalars().first():
                        continue  # Already sent recently

                    new_notif = Notification(
                        user_id=activity.user_id,
                        title=title,
                        content=content,
                        channel="in_app",
                        priority=priority,
                        category="inactivity",
                        status="pending",
                        action_buttons=[
                            {"action": "resume", "title": "Resume Learning"},
                        ],
                    )
                    session.add(new_notif)
                    logger.info(
                        "Sent inactivity notification",
                        user_id=activity.user_id,
                        days_inactive=days_inactive,
                    )

                await session.commit()

        except Exception as e:
            logger.error("Error in check_inactivity", error=str(e), exc_info=True)

    async def expire_opportunities(self) -> None:
        """Mark expired opportunities as expired."""
        logger.debug("Checking for expired opportunities")
        try:
            if not db_manager.engine:
                logger.debug("Database not available, skipping opportunity expiration")
                return

            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)

                stmt = (
                    update(DiscoveredOpportunity)
                    .where(
                        and_(
                            DiscoveredOpportunity.expires_at < now,
                            DiscoveredOpportunity.status.notin_(["expired", "dismissed", "applied"]),
                        )
                    )
                    .values(status="expired")
                )

                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info("Expired opportunities", count=result.rowcount)

                await session.commit()

        except Exception as e:
            logger.error("Error in expire_opportunities", error=str(e), exc_info=True)


# Global instance
scheduler_service = SchedulerService()

