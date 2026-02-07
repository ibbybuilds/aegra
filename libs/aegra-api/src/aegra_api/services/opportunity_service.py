"""Service for managing opportunities and discovery.

Enhanced with AI-powered strategies, save/bookmark functionality,
and richer querying capabilities.
"""

from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.accountability_orm import DiscoveredOpportunity

logger = structlog.getLogger(__name__)


class OpportunityService:
    """Service for managing discovered opportunities."""

    # ------------------------------------------------------------------
    # Listing / querying
    # ------------------------------------------------------------------
    @staticmethod
    async def list_opportunities(
        session: AsyncSession,
        user_id: str,
        opportunity_type: str | None = None,
        status: str = "new",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[DiscoveredOpportunity], int, bool]:
        """List discovered opportunities with filtering + pagination."""
        base_filter = [DiscoveredOpportunity.user_id == user_id]

        if opportunity_type:
            base_filter.append(
                DiscoveredOpportunity.opportunity_type == opportunity_type
            )

        if status == "new":
            base_filter.append(
                DiscoveredOpportunity.status.in_(["new", "notified"])
            )
        elif status == "saved":
            base_filter.append(DiscoveredOpportunity.status == "saved")
        elif status:
            base_filter.append(DiscoveredOpportunity.status == status)

        # Count
        count_q = select(func.count(DiscoveredOpportunity.id)).where(*base_filter)
        total = (await session.execute(count_q)).scalar() or 0

        # Fetch rows
        query = (
            select(DiscoveredOpportunity)
            .where(*base_filter)
            .order_by(
                DiscoveredOpportunity.match_score.desc().nulls_last(),
                DiscoveredOpportunity.discovered_at.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
        result = await session.execute(query)
        opportunities = list(result.scalars().all())

        has_more = len(opportunities) > limit
        opportunities = opportunities[:limit]

        return opportunities, total, has_more

    @staticmethod
    async def get_opportunity(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> DiscoveredOpportunity | None:
        result = await session.execute(
            select(DiscoveredOpportunity).where(
                DiscoveredOpportunity.id == opportunity_id,
                DiscoveredOpportunity.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_opportunity_with_strategy(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Return opportunity data including embedded AI strategy from metadata."""
        opp = await OpportunityService.get_opportunity(
            session, opportunity_id, user_id
        )
        if not opp:
            return None

        meta = opp.metadata_json or {}
        data: dict[str, Any] = {
            "id": opp.id,
            "opportunity_type": opp.opportunity_type,
            "title": opp.title,
            "description": opp.description,
            "url": opp.url,
            "location": opp.location,
            "company": opp.company,
            "salary_range": opp.salary_range,
            "match_score": float(opp.match_score) if opp.match_score else None,
            "matched_track": opp.matched_track,
            "status": opp.status,
            "discovered_at": opp.discovered_at.isoformat() if opp.discovered_at else None,
            "expires_at": opp.expires_at.isoformat() if opp.expires_at else None,
            "metadata": meta,
        }

        # Attach strategy if present
        if opp.opportunity_type == "event":
            data["networking_strategy"] = meta.get("networking_strategy")
        elif opp.opportunity_type == "job":
            data["application_strategy"] = meta.get("application_strategy")

        return data

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------
    @staticmethod
    async def update_opportunity_status(
        session: AsyncSession, opportunity_id: str, user_id: str, status: str
    ) -> dict[str, Any]:
        stmt = (
            update(DiscoveredOpportunity)
            .where(
                DiscoveredOpportunity.id == opportunity_id,
                DiscoveredOpportunity.user_id == user_id,
            )
            .values(status=status)
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Opportunity not found")
        await session.commit()
        return {"status": status}

    @staticmethod
    async def dismiss_opportunity(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> dict[str, Any]:
        return await OpportunityService.update_opportunity_status(
            session, opportunity_id, user_id, "dismissed"
        )

    @staticmethod
    async def mark_opportunity_applied(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> dict[str, Any]:
        return await OpportunityService.update_opportunity_status(
            session, opportunity_id, user_id, "applied"
        )

    @staticmethod
    async def save_opportunity(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> dict[str, Any]:
        """Bookmark / save an opportunity for later."""
        return await OpportunityService.update_opportunity_status(
            session, opportunity_id, user_id, "saved"
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    @staticmethod
    async def get_stats(
        session: AsyncSession, user_id: str
    ) -> dict[str, Any]:
        """Return aggregated opportunity stats for the user."""
        base = [DiscoveredOpportunity.user_id == user_id]

        async def _count(*extra_filters):
            q = select(func.count(DiscoveredOpportunity.id)).where(
                *base, *extra_filters
            )
            return (await session.execute(q)).scalar() or 0

        return {
            "total": await _count(),
            "events": await _count(
                DiscoveredOpportunity.opportunity_type == "event"
            ),
            "jobs": await _count(
                DiscoveredOpportunity.opportunity_type == "job"
            ),
            "learning": await _count(
                DiscoveredOpportunity.opportunity_type == "learning"
            ),
            "saved": await _count(DiscoveredOpportunity.status == "saved"),
            "applied": await _count(DiscoveredOpportunity.status == "applied"),
            "dismissed": await _count(DiscoveredOpportunity.status == "dismissed"),
        }
