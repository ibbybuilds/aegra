"""Enhanced Scheduler service for the Accountability Partner system.

Features:
- Tiered deadline reminders (7d, 3d, 24h, 2h, overdue, severe overdue)
- Inactivity detection (3d, 7d, 10d, 15d)
- Progress celebration checks
- Notification cleanup
- Opportunity expiration + daily discovery
- Frequency-aware notification creation via NotificationEngine
"""

from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from aegra_api.core.accountability_orm import (
    ActionItem,
    DiscoveredOpportunity,
    Notification,
    UserActivityTracking,
)
from aegra_api.core.database import db_manager
from aegra_api.services.notification_engine import notification_engine
from aegra_api.services.opportunity_discovery import opportunity_engine

logger = structlog.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            # Deadline reminders — every 15 min
            self.scheduler.add_job(
                self.check_deadlines,
                IntervalTrigger(minutes=15),
                id="check_deadlines",
                replace_existing=True,
            )
            # Inactivity check — every 6 h
            self.scheduler.add_job(
                self.check_inactivity,
                IntervalTrigger(hours=6),
                id="check_inactivity",
                replace_existing=True,
            )
            # Celebration check — every 4 h
            self.scheduler.add_job(
                self.check_celebrations,
                IntervalTrigger(hours=4),
                id="check_celebrations",
                replace_existing=True,
            )
            # Cleanup old notifications — daily
            self.scheduler.add_job(
                self.check_cleanup,
                IntervalTrigger(hours=24),
                id="check_cleanup",
                replace_existing=True,
            )
            # Expire opportunities — hourly
            self.scheduler.add_job(
                self.expire_opportunities,
                IntervalTrigger(hours=1),
                id="expire_opportunities",
                replace_existing=True,
            )
            # Discovery — once daily
            self.scheduler.add_job(
                self.run_discovery_job,
                IntervalTrigger(hours=24),
                id="run_discovery_job",
                replace_existing=True,
            )

            self.scheduler.start()
            logger.info("Scheduler started with all accountability jobs")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()

    # ------------------------------------------------------------------
    # Deadline reminders
    # ------------------------------------------------------------------
    async def check_deadlines(self) -> None:
        """Generate tiered deadline notifications through NotificationEngine."""
        try:
            if not db_manager.engine:
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)

                result = await session.execute(
                    select(ActionItem).where(
                        and_(
                            ActionItem.status.in_(["pending", "in_progress"]),
                            ActionItem.due_date.isnot(None),
                        )
                    )
                )
                items = result.scalars().all()

                for item in items:
                    if not item.due_date:
                        continue

                    tier, priority, title, content_tpl = (
                        notification_engine.compute_deadline_tier(item.due_date, now)
                    )
                    if not tier:
                        continue

                    # Check if we should send based on last reminder timing
                    should_send = await self._should_send_reminder(item, tier, now)
                    if not should_send:
                        continue

                    # Compute template values
                    hours_diff = (item.due_date - now).total_seconds() / 3600
                    days = max(1, abs(int(hours_diff / 24)))
                    content = content_tpl.format(
                        description=item.description, days=days
                    )

                    notif = await notification_engine.create_notification(
                        session=session,
                        user_id=item.user_id,
                        title=title,
                        content=content,
                        category="deadline",
                        priority=priority,
                        persona=item.advisor_persona,
                        action_buttons=[
                            {"action": "complete", "title": "Mark Complete"},
                            {"action": "snooze", "title": "Snooze 1hr"},
                            {
                                "action": "chat",
                                "title": "Talk to Advisor",
                                "url": "/dashboard/ai-career-advisor",
                            },
                        ],
                        metadata={"action_item_id": item.id, "reminder_tier": tier},
                        check_frequency=True,
                    )

                    if notif:
                        item.reminder_sent_count += 1
                        item.last_reminder_sent = now
                        logger.info(
                            "deadline_reminder_sent",
                            item_id=item.id,
                            tier=tier,
                            count=item.reminder_sent_count,
                        )

                await session.commit()
        except Exception as e:
            logger.error("check_deadlines error", error=str(e), exc_info=True)

    async def _should_send_reminder(
        self, item: ActionItem, tier: str, now: datetime
    ) -> bool:
        if item.reminder_sent_count == 0:
            return True
        if item.last_reminder_sent:
            hours_since = (now - item.last_reminder_sent).total_seconds() / 3600
            if hours_since < 2:
                return False
        return not (tier.startswith("overdue") and item.reminder_sent_count >= 5)

    # ------------------------------------------------------------------
    # Inactivity detection
    # ------------------------------------------------------------------
    async def check_inactivity(self) -> None:
        try:
            if not db_manager.engine:
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                three_days_ago = now - timedelta(days=3)

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
                    tier, priority, title, content_tpl = (
                        notification_engine.compute_inactivity_tier(days_inactive)
                    )
                    if not tier:
                        continue

                    # Deduplicate — only one inactivity notification per 3 days
                    exists = await session.execute(
                        select(Notification).where(
                            and_(
                                Notification.user_id == activity.user_id,
                                Notification.category == "inactivity",
                                Notification.created_at > (now - timedelta(days=3)),
                            )
                        )
                    )
                    if exists.scalars().first():
                        continue

                    content = content_tpl.format(days=days_inactive)

                    await notification_engine.create_notification(
                        session=session,
                        user_id=activity.user_id,
                        title=title,
                        content=content,
                        category="inactivity",
                        priority=priority,
                        action_buttons=[
                            {
                                "action": "resume",
                                "title": "Resume Learning",
                                "url": "/dashboard/my-tracks",
                            },
                            {
                                "action": "chat",
                                "title": "Talk to Advisor",
                                "url": "/dashboard/ai-career-advisor",
                            },
                        ],
                        check_frequency=True,
                    )
                    logger.info(
                        "inactivity_notification",
                        user_id=activity.user_id,
                        days=days_inactive,
                        tier=tier,
                    )

                await session.commit()
        except Exception as e:
            logger.error("check_inactivity error", error=str(e), exc_info=True)

    # ------------------------------------------------------------------
    # Progress celebrations
    # ------------------------------------------------------------------
    async def check_celebrations(self) -> None:
        try:
            if not db_manager.engine:
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                result = await session.execute(select(UserActivityTracking.user_id))
                user_ids = result.scalars().all()

                for user_id in user_ids:
                    celebrations = await notification_engine.check_celebrations(
                        session, user_id
                    )
                    for cel in celebrations:
                        # Deduplicate by type
                        exists = await session.execute(
                            select(Notification).where(
                                and_(
                                    Notification.user_id == user_id,
                                    Notification.category == "celebration",
                                    Notification.metadata_json["celebration_type"].astext
                                    == cel["type"],
                                    Notification.created_at
                                    > (datetime.now(UTC) - timedelta(days=1)),
                                )
                            )
                        )
                        if exists.scalars().first():
                            continue

                        await notification_engine.create_notification(
                            session=session,
                            user_id=user_id,
                            title=cel["title"],
                            content=cel["content"],
                            category="celebration",
                            priority=cel.get("priority", "normal"),
                            metadata={"celebration_type": cel["type"]},
                            check_frequency=True,
                        )

                await session.commit()
        except Exception as e:
            logger.error("check_celebrations error", error=str(e), exc_info=True)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    async def check_cleanup(self) -> None:
        try:
            if not db_manager.engine:
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                cutoff_read = now - timedelta(days=7)
                cutoff_old = now - timedelta(days=30)

                stmt = delete(Notification).where(
                    or_(
                        and_(
                            Notification.status.in_(["read", "dismissed"]),
                            Notification.created_at < cutoff_read,
                        ),
                        Notification.created_at < cutoff_old,
                    )
                )
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info("notification_cleanup", deleted=result.rowcount)
                await session.commit()
        except Exception as e:
            logger.error("check_cleanup error", error=str(e), exc_info=True)

    # ------------------------------------------------------------------
    # Opportunity expiration
    # ------------------------------------------------------------------
    async def expire_opportunities(self) -> None:
        try:
            if not db_manager.engine:
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                now = datetime.now(UTC)
                stmt = (
                    update(DiscoveredOpportunity)
                    .where(
                        and_(
                            DiscoveredOpportunity.expires_at < now,
                            DiscoveredOpportunity.status.notin_(
                                ["expired", "dismissed", "applied"]
                            ),
                        )
                    )
                    .values(status="expired")
                )
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info("opportunities_expired", count=result.rowcount)
                await session.commit()
        except Exception as e:
            logger.error("expire_opportunities error", error=str(e), exc_info=True)

    # ------------------------------------------------------------------
    # Discovery job
    # ------------------------------------------------------------------
    async def run_discovery_job(self) -> None:
        """Periodic opportunity discovery for all active users."""
        logger.info("discovery_job_started")
        try:
            if not db_manager.engine:
                logger.warning("discovery_job_aborted", reason="no db engine")
                return
            session_maker = async_sessionmaker(db_manager.engine, expire_on_commit=False)
            async with session_maker() as session:
                result = await session.execute(select(UserActivityTracking.user_id))
                user_ids = result.scalars().all()
                logger.info("discovery_job_users_found", count=len(user_ids), user_ids=user_ids)

                if not user_ids:
                    logger.warning("discovery_job_no_users", reason="user_activity_tracking table is empty")
                    return

                for user_id in user_ids:
                    try:
                        logger.info("discovery_job_user_start", user_id=user_id)
                        discovered = await opportunity_engine.discover_for_user(
                            session=session,
                            user_id=user_id,
                            auth_token="",
                            max_tracks=2,
                            queries_per_category=1,
                        )
                        logger.info(
                            "discovery_job_user_done",
                            user_id=user_id,
                            opportunities_found=len(discovered),
                        )
                        for opp in discovered:
                            # Use notification_engine so web push is triggered
                            type_label = opp.opportunity_type
                            if type_label == "event":
                                title = "🎯 New Event Matches Your Track"
                                content = (
                                    f"We found a {opp.matched_track} event: "
                                    f"{opp.title}"
                                )
                            elif type_label == "job":
                                company_part = f" at {opp.company}" if opp.company else ""
                                title = "💼 Job Opportunity Alert"
                                content = (
                                    f"New {opp.matched_track} role: "
                                    f"{opp.title}{company_part}"
                                )
                            else:
                                title = "🎓 Learning Opportunity"
                                content = (
                                    f"Free resource for your {opp.matched_track} journey: "
                                    f"{opp.title}"
                                )

                            await notification_engine.create_notification(
                                session=session,
                                user_id=user_id,
                                title=title,
                                content=content,
                                priority="normal",
                                category="opportunity",
                                action_buttons=[
                                    {"action": "view", "title": "View", "url": opp.url},
                                    {"action": "dismiss", "title": "Dismiss"},
                                ],
                                metadata={
                                    "opportunity_id": opp.id,
                                    "opportunity_type": opp.opportunity_type,
                                    "url": opp.url,
                                },
                                check_frequency=False,
                            )
                            opp.status = "notified"
                        await session.commit()
                        logger.info("discovery_job_notifications_sent", user_id=user_id, count=len(discovered))
                    except Exception as e:
                        logger.error(
                            "discovery_failed_for_user",
                            user_id=user_id,
                            error=str(e),
                            exc_info=True,
                        )
        except Exception as e:
            logger.error("run_discovery_job error", error=str(e), exc_info=True)


# Global instance
scheduler_service = SchedulerService()

