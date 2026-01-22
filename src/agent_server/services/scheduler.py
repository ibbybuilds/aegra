"""Scheduler service for the Accountability Partner system."""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from src.agent_server.core.orm import _get_session_maker
from src.agent_server.core.accountability_orm import ActionItem, Notification
from sqlalchemy import select, and_, delete, or_
from datetime import datetime, timezone, timedelta

logger = structlog.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        if not self.scheduler.running:
            # Add jobs
            self.scheduler.add_job(
                self.check_deadlines,
                IntervalTrigger(minutes=1),
                id="check_deadlines",
                replace_existing=True
            )
            # Add cleanup job (runs daily)
            self.scheduler.add_job(
                self.check_cleanup,
                IntervalTrigger(hours=24),
                id="check_cleanup",
                replace_existing=True
            )
            self.scheduler.start()
            logger.info("Scheduler service started")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler service stopped")
        
    async def check_cleanup(self):
        """Cleanup old notifications to maintain database health."""
        logger.debug("Running notification cleanup")
        try:
            session_maker = _get_session_maker()
            async with session_maker() as session:
                now = datetime.now(timezone.utc)
                cutoff_read = now - timedelta(days=7)    # Keep read notifications for 7 days
                cutoff_old = now - timedelta(days=30)    # Keep unread notifications for 30 days
                
                stmt = delete(Notification).where(
                    or_(
                        and_(Notification.status == 'read', Notification.created_at < cutoff_read),
                        Notification.created_at < cutoff_old
                    )
                )
                
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    logger.info("Cleanup completed", deleted_count=result.rowcount)
                
                await session.commit()
        except Exception as e:
            logger.error("Error in check_cleanup", error=str(e), exc_info=True)

    async def check_deadlines(self):
        """Check for upcoming deadlines and generate notifications."""
        logger.debug("Checking deadlines")
        try:
            session_maker = _get_session_maker()
            async with session_maker() as session:
                now = datetime.now(timezone.utc)
                
                # Check Overdue Items
                result = await session.execute(
                    select(ActionItem).where(
                        and_(
                            ActionItem.status == 'pending',
                            ActionItem.due_date < now
                        )
                    )
                )
                overdue_items = result.scalars().all()
                
                for item in overdue_items:
                    msg = f"Overdue: {item.description}"
                    
                    # Avoid duplicate unread notifications
                    exists_query = await session.execute(
                        select(Notification).where(
                            and_(
                                Notification.user_id == item.user_id,
                                Notification.content == msg,
                                Notification.status != 'read'
                            )
                        )
                    )
                    
                    if not exists_query.scalars().first():
                        new_notif = Notification(
                            user_id=item.user_id,
                            title="Action Item Overdue",
                            content=msg,
                            channel="in_app",
                            status="pending",
                            created_at=now
                        )
                        session.add(new_notif)
                        logger.info("Generated overdue notification", action_item_id=item.id)
                
                await session.commit()

        except Exception as e:
            logger.error("Error in check_deadlines", error=str(e), exc_info=True)

# Global instance
scheduler_service = SchedulerService()
