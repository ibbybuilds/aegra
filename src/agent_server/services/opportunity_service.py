"""Service for managing opportunities and discovery."""

from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.accountability_orm import DiscoveredOpportunity

logger = structlog.getLogger(__name__)


class OpportunityService:
    """Service for managing discovered opportunities."""

    @staticmethod
    async def list_opportunities(
        session: AsyncSession,
        user_id: str,
        opportunity_type: str | None = None,
        status: str = "new",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[DiscoveredOpportunity], int, bool]:
        """List discovered opportunities for a user.

        Args:
            session: Database session
            user_id: User ID
            opportunity_type: Filter by type ('event' or 'job')
            status: Filter by status
            limit: Max number of results
            offset: Pagination offset

        Returns:
            Tuple of (opportunities, total_count, has_more)
        """
        # Build base query
        query = select(DiscoveredOpportunity).where(
            DiscoveredOpportunity.user_id == user_id
        )

        if opportunity_type:
            query = query.where(DiscoveredOpportunity.opportunity_type == opportunity_type)

        if status:
            query = query.where(DiscoveredOpportunity.status == status)

        # Order by match score descending, then by discovered_at
        query = query.order_by(
            DiscoveredOpportunity.match_score.desc().nulls_last(),
            DiscoveredOpportunity.discovered_at.desc(),
        )

        # Get total count
        count_query = select(DiscoveredOpportunity.id).where(
            DiscoveredOpportunity.user_id == user_id
        )
        if opportunity_type:
            count_query = count_query.where(
                DiscoveredOpportunity.opportunity_type == opportunity_type
            )
        if status:
            count_query = count_query.where(DiscoveredOpportunity.status == status)

        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # Apply pagination (+1 to check for more)
        query = query.offset(offset).limit(limit + 1)
        result = await session.execute(query)
        opportunities = list(result.scalars().all())

        has_more = len(opportunities) > limit
        opportunities = opportunities[:limit]

        return opportunities, total, has_more

    @staticmethod
    async def get_opportunity(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> DiscoveredOpportunity | None:
        """Get a single opportunity by ID.

        Args:
            session: Database session
            opportunity_id: Opportunity ID
            user_id: User ID (for authorization)

        Returns:
            DiscoveredOpportunity or None if not found
        """
        result = await session.execute(
            select(DiscoveredOpportunity).where(
                DiscoveredOpportunity.id == opportunity_id,
                DiscoveredOpportunity.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_opportunity_status(
        session: AsyncSession, opportunity_id: str, user_id: str, status: str
    ) -> dict[str, Any]:
        """Update the status of an opportunity.

        Args:
            session: Database session
            opportunity_id: Opportunity ID
            user_id: User ID (for authorization)
            status: New status

        Returns:
            Dict with update status

        Raises:
            ValueError: If opportunity not found
        """
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
        """Mark an opportunity as dismissed.

        Args:
            session: Database session
            opportunity_id: Opportunity ID
            user_id: User ID

        Returns:
            Dict with status

        Raises:
            ValueError: If opportunity not found
        """
        return await OpportunityService.update_opportunity_status(
            session, opportunity_id, user_id, "dismissed"
        )

    @staticmethod
    async def mark_opportunity_applied(
        session: AsyncSession, opportunity_id: str, user_id: str
    ) -> dict[str, Any]:
        """Mark an opportunity as applied.

        Args:
            session: Database session
            opportunity_id: Opportunity ID
            user_id: User ID

        Returns:
            Dict with status

        Raises:
            ValueError: If opportunity not found
        """
        return await OpportunityService.update_opportunity_status(
            session, opportunity_id, user_id, "applied"
        )
