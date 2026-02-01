"""Opportunity Discovery Service.

This service discovers events and job opportunities for users based on:
1. Their currently enrolled courses/tracks
2. Their current location

It uses Brave Search API to find relevant opportunities and scores them for relevance.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_server.core.accountability_orm import (
    DiscoveredOpportunity,
    Notification,
    UserPreferences,
)
from src.agent_server.core.config import settings

logger = structlog.get_logger()


# Track keyword mapping for search queries
TRACK_KEYWORDS: dict[str, list[str]] = {
    "data-analytics": [
        "data analytics",
        "SQL",
        "Power BI",
        "Tableau",
        "Excel",
        "business intelligence",
        "BI analyst",
        "data analyst",
    ],
    "data-science": [
        "data science",
        "machine learning",
        "Python",
        "ML engineer",
        "data scientist",
        "statistics",
        "predictive analytics",
    ],
    "data-engineering": [
        "data engineering",
        "ETL",
        "Spark",
        "Airflow",
        "data pipeline",
        "data engineer",
        "dbt",
        "Snowflake",
    ],
    "ai-engineering": [
        "AI engineer",
        "LLM",
        "GenAI",
        "artificial intelligence",
        "prompt engineering",
        "ML Ops",
        "deep learning",
    ],
    "business-intelligence": [
        "business intelligence",
        "BI developer",
        "reporting",
        "dashboards",
        "Power BI",
        "Looker",
    ],
}


class OpportunityDiscoveryEngine:
    """Discovers relevant opportunities (events, jobs) for users."""

    def __init__(self, brave_api_key: str | None = None):
        self.brave_api_key = brave_api_key or getattr(settings, "brave_api_key", None)
        self.lms_base_url = getattr(settings, "lms_api_url", None)

    async def get_user_enrollments(self, user_id: str, auth_token: str) -> list[dict]:
        """Fetch user's enrolled courses/tracks from LMS API."""
        if not self.lms_base_url:
            logger.warning("LMS API URL not configured, using mock data")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.lms_base_url}/api/v1/enrollment/student/blackboard",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("enrollments", [])
        except httpx.HTTPError as e:
            logger.error("Failed to fetch enrollments", error=str(e), user_id=user_id)
            return []

    async def get_user_location(
        self, session: AsyncSession, user_id: str
    ) -> str | None:
        """Get user's location from preferences."""
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        return prefs.location if prefs else None

    def build_event_queries(self, track: str, location: str) -> list[str]:
        """Generate location + track specific event search queries."""
        track_key = track.lower().replace(" ", "-")
        keywords = TRACK_KEYWORDS.get(track_key, [track.lower()])

        queries = []
        # Limit to top 3 keywords to avoid too many API calls
        for kw in keywords[:3]:
            queries.append(f"{kw} meetup {location}")
            queries.append(f"{kw} networking event {location} 2026")
            queries.append(f"{kw} workshop conference {location}")

        return queries

    def build_job_queries(self, track: str, location: str) -> list[str]:
        """Generate location + track specific job search queries."""
        track_key = track.lower().replace(" ", "-")
        keywords = TRACK_KEYWORDS.get(track_key, [track.lower()])

        queries = []
        # Focus on entry-level and junior roles
        for kw in keywords[:2]:
            queries.append(f"junior {kw} job {location}")
            queries.append(f"entry level {kw} {location} hiring")

        return queries

    async def brave_search(self, query: str) -> list[dict[str, Any]]:
        """Execute a Brave Search API query."""
        if not self.brave_api_key:
            logger.warning("Brave API key not configured")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.brave_api_key,
                    },
                    params={
                        "q": query,
                        "count": 5,
                        "freshness": "pm",  # Past month
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("web", {}).get("results", [])
        except httpx.HTTPError as e:
            logger.error("Brave search failed", error=str(e), query=query)
            return []

    def parse_event_result(
        self, result: dict[str, Any], track: str, location: str
    ) -> dict[str, Any] | None:
        """Parse a search result into an event opportunity."""
        title = result.get("title", "")
        description = result.get("description", "")
        url = result.get("url", "")

        # Basic relevance check - must mention something event-like
        event_keywords = ["meetup", "event", "workshop", "conference", "webinar", "summit"]
        if not any(kw in title.lower() or kw in description.lower() for kw in event_keywords):
            return None

        return {
            "opportunity_type": "event",
            "title": title,
            "description": description,
            "url": url,
            "location": location,
            "matched_track": track,
            "match_score": self.calculate_match_score(result, track),
        }

    def parse_job_result(
        self, result: dict[str, Any], track: str, location: str
    ) -> dict[str, Any] | None:
        """Parse a search result into a job opportunity."""
        title = result.get("title", "")
        description = result.get("description", "")
        url = result.get("url", "")

        # Basic relevance check - must look like a job
        job_keywords = ["job", "career", "hiring", "position", "role", "apply"]
        if not any(kw in title.lower() or kw in description.lower() for kw in job_keywords):
            return None

        # Try to extract company from title
        company = None
        if " at " in title.lower():
            company = title.split(" at ")[-1].split(" - ")[0].strip()
        elif " - " in title:
            parts = title.split(" - ")
            if len(parts) > 1:
                company = parts[-1].strip()

        return {
            "opportunity_type": "job",
            "title": title,
            "description": description,
            "url": url,
            "location": location,
            "company": company,
            "matched_track": track,
            "match_score": self.calculate_match_score(result, track),
        }

    def calculate_match_score(self, result: dict[str, Any], track: str) -> Decimal:
        """Calculate a relevance score for the result (0.00 - 1.00)."""
        score = 0.5  # Base score

        title = result.get("title", "").lower()
        description = result.get("description", "").lower()
        content = title + " " + description

        track_key = track.lower().replace(" ", "-")
        keywords = TRACK_KEYWORDS.get(track_key, [track.lower()])

        # Increase score for each matching keyword
        for kw in keywords:
            if kw.lower() in content:
                score += 0.1

        # Cap at 1.0
        return Decimal(str(min(score, 1.0)))

    async def discover_for_user(
        self,
        session: AsyncSession,
        user_id: str,
        auth_token: str,
    ) -> list[DiscoveredOpportunity]:
        """Discover opportunities for a specific user."""
        # Get user's enrolled tracks
        enrollments = await self.get_user_enrollments(user_id, auth_token)
        if not enrollments:
            logger.info("No enrollments found", user_id=user_id)
            return []

        # Get user's location
        location = await self.get_user_location(session, user_id)
        if not location:
            logger.info("No location set for user", user_id=user_id)
            # Use a default or skip
            location = "remote"  # Default to remote opportunities

        discovered = []
        seen_urls: set[str] = set()

        for enrollment in enrollments:
            track_name = enrollment.get("trackName", "")
            if not track_name:
                continue

            # Search for events
            event_queries = self.build_event_queries(track_name, location)
            for query in event_queries[:2]:  # Limit queries
                results = await self.brave_search(query)
                for result in results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    event = self.parse_event_result(result, track_name, location)
                    if event:
                        opp = DiscoveredOpportunity(
                            user_id=user_id,
                            opportunity_type=event["opportunity_type"],
                            title=event["title"],
                            description=event["description"],
                            url=event["url"],
                            location=event["location"],
                            matched_track=event["matched_track"],
                            match_score=event["match_score"],
                            expires_at=datetime.now(UTC) + timedelta(days=30),
                            metadata_json={"source": "brave_search", "query": query},
                        )
                        session.add(opp)
                        discovered.append(opp)

            # Search for jobs
            job_queries = self.build_job_queries(track_name, location)
            for query in job_queries[:2]:  # Limit queries
                results = await self.brave_search(query)
                for result in results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    job = self.parse_job_result(result, track_name, location)
                    if job:
                        opp = DiscoveredOpportunity(
                            user_id=user_id,
                            opportunity_type=job["opportunity_type"],
                            title=job["title"],
                            description=job["description"],
                            url=job["url"],
                            location=job["location"],
                            company=job.get("company"),
                            matched_track=job["matched_track"],
                            match_score=job["match_score"],
                            expires_at=datetime.now(UTC) + timedelta(days=14),
                            metadata_json={"source": "brave_search", "query": query},
                        )
                        session.add(opp)
                        discovered.append(opp)

        await session.commit()

        logger.info(
            "opportunities_discovered",
            user_id=user_id,
            count=len(discovered),
            events=len([o for o in discovered if o.opportunity_type == "event"]),
            jobs=len([o for o in discovered if o.opportunity_type == "job"]),
        )

        return discovered

    async def create_opportunity_notification(
        self,
        session: AsyncSession,
        opportunity: DiscoveredOpportunity,
    ) -> Notification:
        """Create a notification for a discovered opportunity."""
        if opportunity.opportunity_type == "event":
            title = "🎯 New Event Matches Your Track"
            content = f"We found an event that matches your {opportunity.matched_track} learning path: {opportunity.title}"
            action_buttons = [
                {"action": "view", "title": "View Event", "url": opportunity.url},
                {"action": "dismiss", "title": "Not Interested"},
            ]
        else:
            title = "💼 Job Opportunity Alert"
            content = f"New {opportunity.matched_track} role: {opportunity.title}"
            if opportunity.company:
                content += f" at {opportunity.company}"
            action_buttons = [
                {"action": "view", "title": "View Job", "url": opportunity.url},
                {"action": "dismiss", "title": "Not Interested"},
            ]

        notification = Notification(
            user_id=opportunity.user_id,
            title=title,
            content=content,
            channel="in_app",
            priority="normal",
            category="opportunity",
            action_buttons=action_buttons,
            metadata_json={
                "opportunity_id": opportunity.id,
                "opportunity_type": opportunity.opportunity_type,
            },
            expires_at=opportunity.expires_at,
        )
        session.add(notification)

        # Update opportunity status
        opportunity.status = "notified"

        await session.commit()
        return notification


# Singleton instance
opportunity_engine = OpportunityDiscoveryEngine()
