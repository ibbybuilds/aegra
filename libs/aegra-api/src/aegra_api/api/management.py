"""Management dashboard endpoints for analytics and insights"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.auth_deps import get_current_user
from aegra_api.core.orm import ActivityLog as ActivityLogORM
from aegra_api.core.orm import Assistant as AssistantORM
from aegra_api.core.orm import Run as RunORM
from aegra_api.core.orm import Thread as ThreadORM
from aegra_api.core.orm import get_session
from aegra_api.models import User

router = APIRouter(prefix="/api/v1/management", tags=["Management Dashboard"])

logger = structlog.getLogger(__name__)


def require_admin_role(user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure user has admin or superadmin role.
    Raises 403 Forbidden if user doesn't have required role.
    """
    user_role = getattr(user, "role", None) or (
        getattr(user, "permissions", [])[0]
        if getattr(user, "permissions", None)
        else None
    )

    if user_role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=403,
            detail=f"Admin access required. Your role: {user_role or 'user'}",
        )

    return user


@router.get(
    "/dashboard/overview",
    description="Get management dashboard overview metrics (Admin only)",
)
async def get_dashboard_overview(
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get comprehensive overview metrics for the management dashboard.

    **Query Parameters:**
    - `start_date`: Start date for filtering (ISO format)
    - `end_date`: End date for filtering (ISO format)

    **Returns:**
    - `total_users`: Total number of users/students
    - `active_users`: Number of active users (with activity)
    - `total_runs`: Total number of AI runs
    - `completed_runs`: Number of completed runs
    - `failed_runs`: Number of failed runs
    - `total_prompts`: Total number of prompts/queries
    - `total_threads`: Total number of threads created
    - `total_assistants`: Total number of assistants
    - `average_run_success_rate`: Success rate percentage
    - `common_action_types`: Most common action types
    - `time_period`: Period covered by the metrics
    """
    conditions = []

    if start_date:
        conditions.append(ActivityLogORM.created_at >= start_date)
    if end_date:
        conditions.append(ActivityLogORM.created_at <= end_date)

    run_conditions = []
    if start_date:
        run_conditions.append(RunORM.created_at >= start_date)
    if end_date:
        run_conditions.append(RunORM.created_at <= end_date)

    # Count unique users from both activity_log and run tables (for comprehensive coverage)
    # Get users from activity logs
    activity_users_query = select(func.distinct(ActivityLogORM.user_id))
    if conditions:
        activity_users_query = activity_users_query.where(and_(*conditions))
    activity_users = await session.execute(activity_users_query)
    activity_user_ids = {row[0] for row in activity_users if row[0]}

    # Get users from runs (includes legacy runs before activity logging)
    run_users_query = select(func.distinct(RunORM.user_id))
    if run_conditions:
        run_users_query = run_users_query.where(and_(*run_conditions))
    run_users = await session.execute(run_users_query)
    run_user_ids = {row[0] for row in run_users if row[0]}

    # Combine user sets
    all_user_ids = activity_user_ids.union(run_user_ids)
    total_users = len(all_user_ids)

    # Count active users (users with activities, excluding pings)
    active_users_query = select(
        func.count(func.distinct(ActivityLogORM.user_id))
    ).where(ActivityLogORM.action_type != "ping")
    if conditions:
        active_users_query = active_users_query.where(and_(*conditions))
    active_users = await session.scalar(active_users_query) or 0

    # Add users from runs if they're not already in activity logs
    active_users = max(active_users, len(run_user_ids))

    # Count total runs
    total_runs_query = select(func.count(RunORM.run_id))
    if run_conditions:
        total_runs_query = total_runs_query.where(and_(*run_conditions))
    total_runs = await session.scalar(total_runs_query) or 0

    # Count completed runs
    completed_runs_query = select(func.count(RunORM.run_id)).where(
        RunORM.status == "completed"
    )
    if run_conditions:
        completed_runs_query = completed_runs_query.where(and_(*run_conditions))
    completed_runs = await session.scalar(completed_runs_query) or 0

    # Count failed runs
    failed_runs_query = select(func.count(RunORM.run_id)).where(
        RunORM.status == "failed"
    )
    if run_conditions:
        failed_runs_query = failed_runs_query.where(and_(*run_conditions))
    failed_runs = await session.scalar(failed_runs_query) or 0

    # Count prompts/queries
    prompts_query = select(func.count(ActivityLogORM.activity_id)).where(
        ActivityLogORM.action_type.in_(["prompt", "query", "run_started"])
    )
    if conditions:
        prompts_query = prompts_query.where(and_(*conditions))
    total_prompts = await session.scalar(prompts_query) or 0

    # Count threads
    total_threads_query = select(func.count(ThreadORM.thread_id))
    threads_count = await session.scalar(total_threads_query) or 0

    # Count assistants
    total_assistants_query = select(func.count(AssistantORM.assistant_id))
    total_assistants = await session.scalar(total_assistants_query) or 0

    # Calculate success rate
    success_rate = 0.0
    if total_runs > 0:
        success_rate = (completed_runs / total_runs) * 100

    # Get most common action types
    action_query = (
        select(ActivityLogORM.action_type, func.count(ActivityLogORM.activity_id))
        .group_by(ActivityLogORM.action_type)
        .order_by(func.count(ActivityLogORM.activity_id).desc())
        .limit(5)
    )
    if conditions:
        action_query = action_query.where(and_(*conditions))

    action_results = await session.execute(action_query)
    common_actions = [
        {"action": action, "count": count} for action, count in action_results
    ]

    time_period = {
        "start": start_date.isoformat() if start_date else None,
        "end": end_date.isoformat() if end_date else None,
    }

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "total_prompts": total_prompts,
        "total_threads": threads_count,
        "total_assistants": total_assistants,
        "average_run_success_rate": round(success_rate, 2),
        "common_action_types": common_actions,
        "time_period": time_period,
    }


@router.get("/dashboard/user-stats", description="Get per-user statistics (Admin only)")
async def get_user_statistics(
    limit: int = Query(10, ge=1, le=100, description="Top N users"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get per-user statistics showing activity levels.

    **Query Parameters:**
    - `limit`: Number of top users to return (default: 10, max: 100)
    - `start_date`: Start date for filtering (ISO format)
    - `end_date`: End date for filtering (ISO format)

    **Returns:**
    - `top_users`: List of top users with their activity counts
    - `total_unique_users`: Total number of unique users
    """
    conditions = []
    if start_date:
        conditions.append(ActivityLogORM.created_at >= start_date)
    if end_date:
        conditions.append(ActivityLogORM.created_at <= end_date)

    run_conditions = []
    if start_date:
        run_conditions.append(RunORM.created_at >= start_date)
    if end_date:
        run_conditions.append(RunORM.created_at <= end_date)

    # Get top users by activity from activity logs
    user_query = (
        select(
            ActivityLogORM.user_id,
            func.count(ActivityLogORM.activity_id).label("activity_count"),
        )
        .group_by(ActivityLogORM.user_id)
        .order_by(func.count(ActivityLogORM.activity_id).desc())
        .limit(limit)
    )

    if conditions:
        user_query = user_query.where(and_(*conditions))

    user_results = await session.execute(user_query)
    top_users_from_logs = [
        {"user_id": user_id, "activity_count": count} for user_id, count in user_results
    ]

    # Get top users by runs (legacy runs before activity logging)
    run_user_query = (
        select(
            RunORM.user_id,
            func.count(RunORM.run_id).label("run_count"),
        )
        .group_by(RunORM.user_id)
        .order_by(func.count(RunORM.run_id).desc())
        .limit(limit)
    )

    if run_conditions:
        run_user_query = run_user_query.where(and_(*run_conditions))

    run_user_results = await session.execute(run_user_query)
    top_users_from_runs: dict[str, int] = dict(cast(Iterable[tuple[str, int]], run_user_results.all()))

    # Merge results: activity logs first, then add missing users from runs
    top_users_dict = {}
    for user in top_users_from_logs:
        top_users_dict[user["user_id"]] = user["activity_count"]

    for user_id, count in top_users_from_runs.items():
        if user_id not in top_users_dict:
            top_users_dict[user_id] = count
        else:
            top_users_dict[user_id] += count  # Combine counts if user has both

    # Sort and take top N
    top_users = [
        {"user_id": user_id, "activity_count": count}
        for user_id, count in sorted(
            top_users_dict.items(), key=lambda x: x[1], reverse=True
        )[:limit]
    ]

    # Get total unique users from both sources
    activity_users_query = select(func.distinct(ActivityLogORM.user_id))
    if conditions:
        activity_users_query = activity_users_query.where(and_(*conditions))
    activity_users = await session.execute(activity_users_query)
    activity_user_ids = {row[0] for row in activity_users if row[0]}

    run_users_query = select(func.distinct(RunORM.user_id))
    if run_conditions:
        run_users_query = run_users_query.where(and_(*run_conditions))
    run_users = await session.execute(run_users_query)
    run_user_ids = {row[0] for row in run_users if row[0]}

    total_users = len(activity_user_ids.union(run_user_ids))

    return {"top_users": top_users, "total_unique_users": total_users}


@router.get(
    "/dashboard/run-metrics", description="Get run execution metrics (Admin only)"
)
async def get_run_metrics(
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get metrics about run execution and performance.

    **Query Parameters:**
    - `start_date`: Start date for filtering (ISO format)
    - `end_date`: End date for filtering (ISO format)

    **Returns:**
    - `total_runs`: Total number of runs
    - `status_breakdown`: Breakdown by status (pending, running, completed, failed, cancelled)
    - `runs_by_assistant`: Number of runs per assistant
    - `average_runs_per_user`: Average runs per user
    - `time_period`: Period covered by the metrics
    """
    conditions = []
    if start_date:
        conditions.append(RunORM.created_at >= start_date)
    if end_date:
        conditions.append(RunORM.created_at <= end_date)

    # Total runs
    total_query = select(func.count(RunORM.run_id))
    if conditions:
        total_query = total_query.where(and_(*conditions))
    total_runs = await session.scalar(total_query) or 0

    # Status breakdown
    statuses = ["pending", "running", "completed", "failed", "cancelled"]
    status_breakdown = {}

    for status in statuses:
        status_query = select(func.count(RunORM.run_id)).where(RunORM.status == status)
        if conditions:
            status_query = status_query.where(and_(*conditions))
        status_breakdown[status] = await session.scalar(status_query) or 0

    # Runs by assistant
    assistant_query = (
        select(RunORM.assistant_id, func.count(RunORM.run_id).label("run_count"))
        .group_by(RunORM.assistant_id)
        .order_by(func.count(RunORM.run_id).desc())
    )
    if conditions:
        assistant_query = assistant_query.where(and_(*conditions))

    assistant_results = await session.execute(assistant_query)
    runs_by_assistant = [
        {"assistant_id": asst_id or "unknown", "count": count}
        for asst_id, count in assistant_results
    ]

    # Average runs per user
    users_query = select(func.count(func.distinct(RunORM.user_id)))
    if conditions:
        users_query = users_query.where(and_(*conditions))
    total_users = await session.scalar(users_query) or 1

    average_runs = total_runs / total_users if total_users > 0 else 0

    time_period = {
        "start": start_date.isoformat() if start_date else None,
        "end": end_date.isoformat() if end_date else None,
    }

    return {
        "total_runs": total_runs,
        "status_breakdown": status_breakdown,
        "runs_by_assistant": runs_by_assistant,
        "average_runs_per_user": round(average_runs, 2),
        "time_period": time_period,
    }


@router.get(
    "/dashboard/daily-metrics", description="Get daily activity metrics (Admin only)"
)
async def get_daily_metrics(
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get daily aggregated metrics for trend analysis.

    **Query Parameters:**
    - `days`: Number of days to include (default: 7, max: 90)

    **Returns:**
    - `daily_stats`: List of daily statistics with date, activity count, runs, etc.
    """
    start_date = datetime.now(UTC) - timedelta(days=days)

    # Get daily activity counts
    daily_query = (
        select(
            func.date(ActivityLogORM.created_at).label("date"),
            func.count(ActivityLogORM.activity_id).label("activity_count"),
            func.count(func.distinct(ActivityLogORM.user_id)).label("active_users"),
        )
        .where(ActivityLogORM.created_at >= start_date)
        .group_by(func.date(ActivityLogORM.created_at))
        .order_by(func.date(ActivityLogORM.created_at))
    )

    daily_results = await session.execute(daily_query)
    daily_data = {}

    for date, activity_count, active_users in daily_results:
        daily_data[date.isoformat()] = {
            "date": date.isoformat(),
            "activity_count": activity_count,
            "active_users": active_users,
        }

    # Get daily run counts
    daily_runs_query = (
        select(
            func.date(RunORM.created_at).label("date"),
            func.count(RunORM.run_id).label("run_count"),
        )
        .where(RunORM.created_at >= start_date)
        .group_by(func.date(RunORM.created_at))
        .order_by(func.date(RunORM.created_at))
    )

    run_results = await session.execute(daily_runs_query)

    for date, run_count in run_results:
        date_str = date.isoformat()
        if date_str not in daily_data:
            daily_data[date_str] = {
                "date": date_str,
                "activity_count": 0,
                "active_users": 0,
            }
        daily_data[date_str]["run_count"] = run_count

    return {
        "daily_stats": list(daily_data.values()),
        "period_days": days,
    }


@router.get(
    "/dashboard/assistant-usage", description="Get assistant usage metrics (Admin only)"
)
async def get_assistant_usage(
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get usage metrics for each assistant.

    **Query Parameters:**
    - `start_date`: Start date for filtering (ISO format)
    - `end_date`: End date for filtering (ISO format)

    **Returns:**
    - `assistants`: List of assistants with usage statistics
    """
    conditions = []
    if start_date:
        conditions.append(ActivityLogORM.created_at >= start_date)
    if end_date:
        conditions.append(ActivityLogORM.created_at <= end_date)

    # Get assistant usage from activity logs
    assistant_query = (
        select(
            ActivityLogORM.assistant_id,
            func.count(ActivityLogORM.activity_id).label("total_activities"),
            func.count(func.distinct(ActivityLogORM.user_id)).label("unique_users"),
        )
        .where(ActivityLogORM.assistant_id.isnot(None))
        .group_by(ActivityLogORM.assistant_id)
        .order_by(func.count(ActivityLogORM.activity_id).desc())
    )

    if conditions:
        assistant_query = assistant_query.where(and_(*conditions))

    results = await session.execute(assistant_query)
    assistants = [
        {
            "assistant_id": asst_id,
            "total_activities": count,
            "unique_users": users,
        }
        for asst_id, count, users in results
    ]

    return {
        "assistants": assistants,
        "total_assistants_used": len(assistants),
    }
