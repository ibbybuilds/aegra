"""Opportunity Discovery Engine — v2.

AI-powered discovery of events, jobs, and learning opportunities
matched to each user's enrolled tracks and location.

Features
--------
* Brave Search API integration with freshness filtering
* Claude web search tool (Anthropic Messages API) for real-time results
* Dual-provider support: brave | claude | both
* Track-aware keyword expansion for events, jobs and learning
* AI-powered relevance scoring via LLM (with deterministic fallback)
* Networking strategy generation for events
* Application strategy generation for jobs
* Deduplication by URL
* Notification creation per discovered opportunity
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.accountability_orm import (
    DiscoveredOpportunity,
    Notification,
    UserPreferences,
)
from aegra_api.settings import settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Track → keyword mapping
# ---------------------------------------------------------------------------
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

# Keywords that signal an event result
EVENT_SIGNALS = frozenset(
    [
        "meetup",
        "event",
        "workshop",
        "conference",
        "webinar",
        "summit",
        "hackathon",
        "bootcamp",
        "seminar",
        "networking",
        "talk",
        "panel",
        "fireside",
    ]
)

# Keywords that signal a job result
JOB_SIGNALS = frozenset(
    [
        "job",
        "career",
        "hiring",
        "position",
        "role",
        "apply",
        "vacancy",
        "opening",
        "recruit",
        "employment",
    ]
)

LEARNING_SIGNALS = frozenset(
    [
        "course",
        "certification",
        "free",
        "tutorial",
        "training",
        "scholarship",
        "voucher",
        "exam",
        "credential",
        "mooc",
    ]
)


def _normalise_track(track: str) -> str:
    """Normalise a track name to a key in TRACK_KEYWORDS."""
    return track.lower().strip().replace(" ", "-")


def _content_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------
class OpportunityDiscoveryEngine:
    """Discovers relevant opportunities (events, jobs, learning) for users."""

    def __init__(
        self,
        brave_api_key: str | None = None,
        anthropic_api_key: str | None = None,
    ) -> None:
        self.brave_api_key = brave_api_key or settings.discovery.BRAVE_API_KEY
        self.anthropic_api_key = anthropic_api_key or settings.discovery.ANTHROPIC_API_KEY
        self.lms_base_url = settings.app.LMS_URL

    # ------------------------------------------------------------------
    # LMS integration
    # ------------------------------------------------------------------
    async def get_user_enrollments(self, user_id: str, auth_token: str) -> list[dict]:
        """Fetch user's enrolled courses/tracks from LMS API."""
        if not self.lms_base_url:
            logger.warning("LMS API URL not configured")
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
                enrollments = data.get("enrollments", [])

                track_names = []
                for e in enrollments:
                    course = e.get("course", {})
                    name = (
                        course.get("title")
                        or course.get("track")
                        or e.get("trackName")
                    )
                    track_names.append(name)

                logger.info(
                    "Fetched enrollments from LMS",
                    user_id=user_id,
                    count=len(enrollments),
                    tracks=track_names,
                )
                return enrollments
        except httpx.HTTPError as e:
            logger.error("Failed to fetch enrollments", error=str(e), user_id=user_id)
            return []

    async def get_user_location(
        self, session: AsyncSession, user_id: str
    ) -> str | None:
        """Get user's location from user_preferences."""
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        return prefs.location if prefs else None

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------
    def _keywords_for_track(self, track: str) -> list[str]:
        key = _normalise_track(track)
        return TRACK_KEYWORDS.get(key, [track.lower()])

    def build_event_queries(self, track: str, location: str) -> list[str]:
        keywords = self._keywords_for_track(track)
        queries: list[str] = []
        for kw in keywords[:3]:
            queries.append(f"site:linkedin.com/events {kw} {location}")
            queries.append(f"{kw} meetup OR networking event {location} 2026")
            queries.append(f"{kw} hackathon OR workshop {location}")
        return queries

    def build_job_queries(self, track: str, location: str) -> list[str]:
        keywords = self._keywords_for_track(track)
        queries: list[str] = []
        for kw in keywords[:3]:
            queries.append(f"{kw} job {location} junior OR entry level")
            queries.append(f"{kw} internship OR graduate {location}")
            queries.append(f"hiring {kw} {location}")
        return queries

    def build_learning_queries(self, track: str) -> list[str]:
        keywords = self._keywords_for_track(track)
        queries: list[str] = []
        for kw in keywords[:2]:
            queries.append(f"free {kw} certification OR course 2026")
            queries.append(f"{kw} exam voucher OR scholarship")
        return queries

    # ------------------------------------------------------------------
    # Brave Search
    # ------------------------------------------------------------------
    async def brave_search(
        self, query: str, freshness: str = "pw", count: int = 5
    ) -> list[dict[str, Any]]:
        """Execute a Brave Search API query.

        Args:
            query: Search query string
            freshness: 'pd' past day, 'pw' past week, 'pm' past month
            count: Number of results (max 20)
        """
        if not self.brave_api_key:
            logger.warning("brave_search_skipped", reason="BRAVE_SEARCH_API_KEY not set")
            return []

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.brave_api_key,
                    },
                    params={"q": query, "count": count, "freshness": freshness},
                    timeout=10.0,
                )
                resp.raise_for_status()
                results = resp.json().get("web", {}).get("results", [])
                logger.info("brave_search_completed", query=query[:80], result_count=len(results))
                return results
        except httpx.HTTPError as e:
            logger.error("brave_search_failed", error=str(e), query=query[:80])
            return []

    # ------------------------------------------------------------------
    # Claude Web Search (Anthropic Messages API)
    # ------------------------------------------------------------------
    async def claude_web_search(
        self,
        query: str,
        *,
        max_uses: int = 3,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a search using Claude's built-in web search tool.

        Returns a list of dicts with keys: title, url, description — same shape
        as brave_search results so the rest of the pipeline can consume them
        interchangeably.

        Args:
            query: Natural-language search query
            max_uses: Max web searches Claude may issue (controls cost)
            location: Optional user location for result localisation
        """
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set — skipping Claude web search")
            return []

        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)

            # Build the web_search tool definition
            web_search_tool: dict[str, Any] = {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_uses,
            }

            # Add location hints if available
            if location and location.lower() not in ("remote", "online", ""):
                parts = [p.strip() for p in location.split(",")]
                loc_spec: dict[str, Any] = {"type": "approximate"}
                if len(parts) >= 1:
                    loc_spec["city"] = parts[0]
                if len(parts) >= 2:
                    loc_spec["region"] = parts[1]
                if len(parts) >= 3:
                    loc_spec["country"] = parts[2]
                web_search_tool["user_location"] = loc_spec

            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                tools=[web_search_tool],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Search the web for: {query}\n\n"
                            "Return ONLY a concise list of the results you find. "
                            "For each result include the title, URL, and a short description."
                        ),
                    }
                ],
            )

            # Extract search results from response content blocks
            results: list[dict[str, Any]] = []
            for block in response.content:
                # Grab raw web_search_tool_result items
                if getattr(block, "type", "") == "web_search_tool_result":
                    search_content = getattr(block, "content", [])
                    if isinstance(search_content, list):
                        for item in search_content:
                            if getattr(item, "type", "") == "web_search_result":
                                results.append(
                                    {
                                        "title": getattr(item, "title", ""),
                                        "url": getattr(item, "url", ""),
                                        "description": getattr(
                                            item, "page_age", ""
                                        ),
                                    }
                                )

            # Also extract cited information from text blocks for richer descriptions
            url_to_desc: dict[str, str] = {}
            for block in response.content:
                if getattr(block, "type", "") == "text":
                    citations = getattr(block, "citations", None) or []
                    for cite in citations:
                        cite_url = getattr(cite, "url", "")
                        cited_text = getattr(cite, "cited_text", "")
                        if cite_url and cited_text:
                            existing = url_to_desc.get(cite_url, "")
                            if len(cited_text) > len(existing):
                                url_to_desc[cite_url] = cited_text

            # Merge cited descriptions into results
            for r in results:
                url = r.get("url", "")
                if url in url_to_desc and len(url_to_desc[url]) > len(
                    r.get("description", "")
                ):
                    r["description"] = url_to_desc[url]

            # Deduplicate by URL
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for r in results:
                u = r.get("url", "")
                if u and u not in seen:
                    seen.add(u)
                    unique.append(r)

            logger.info(
                "claude_web_search_completed",
                query=query,
                result_count=len(unique),
                web_search_requests=getattr(
                    getattr(response.usage, "server_tool_use", None),
                    "web_search_requests",
                    0,
                )
                if hasattr(response.usage, "server_tool_use")
                else response.usage.__dict__.get("server_tool_use", {}).get(
                    "web_search_requests", 0
                ),
            )
            return unique

        except Exception as e:
            logger.error("Claude web search failed", error=str(e), query=query)
            return []

    # ------------------------------------------------------------------
    # Unified search dispatcher
    # ------------------------------------------------------------------
    async def search(
        self,
        query: str,
        *,
        provider: str = "auto",
        freshness: str = "pw",
        count: int = 5,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """Unified search interface — dispatches to brave, claude, or both.

        Args:
            query: Search query
            provider: 'brave', 'claude', 'both', or 'auto' (tries brave first,
                      falls back to claude)
            freshness: Brave freshness filter (ignored for claude)
            count: Number of results for Brave
            location: User location for Claude localisation
        """
        logger.info("search_dispatch", provider=provider, query=query[:80])

        if provider == "brave":
            return await self.brave_search(query, freshness=freshness, count=count)

        if provider == "claude":
            return await self.claude_web_search(query, location=location)

        if provider == "both":
            brave_results = await self.brave_search(
                query, freshness=freshness, count=count
            )
            claude_results = await self.claude_web_search(query, location=location)
            # Merge, deduplicate by URL (brave results get priority)
            seen = {r.get("url") for r in brave_results if r.get("url")}
            merged = list(brave_results)
            for r in claude_results:
                if r.get("url") not in seen:
                    seen.add(r.get("url"))
                    merged.append(r)
            return merged

        # auto: prefer brave, fall back to claude
        results = await self.brave_search(query, freshness=freshness, count=count)
        if not results and self.anthropic_api_key:
            logger.info("Brave returned no results — falling back to Claude web search")
            results = await self.claude_web_search(query, location=location)
        return results

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------
    def _extract_company(self, title: str, url: str) -> str | None:
        """Best-effort company extraction from title."""
        clean = title.replace(" | LinkedIn", "").replace(" | Indeed", "").strip()
        is_linkedin = "linkedin.com" in url

        if " at " in clean:
            parts = clean.split(" at ")
            if len(parts) > 1:
                return parts[-1].split(" - ")[0].strip()
        elif " - " in clean:
            parts = clean.split(" - ")
            if is_linkedin and len(parts) >= 3:
                return parts[1].strip()
            if len(parts) > 1:
                return parts[-1].strip()
        return None

    def parse_event_result(
        self, result: dict[str, Any], track: str, location: str
    ) -> dict[str, Any] | None:
        title = result.get("title", "")
        desc = result.get("description", "")
        url = result.get("url", "")
        content = f"{title} {desc}".lower()

        if not any(kw in content for kw in EVENT_SIGNALS):
            return None

        return {
            "opportunity_type": "event",
            "title": title,
            "description": desc,
            "url": url,
            "location": location,
            "matched_track": track,
            "match_score": self._score(result, track),
        }

    def parse_job_result(
        self, result: dict[str, Any], track: str, location: str
    ) -> dict[str, Any] | None:
        title = result.get("title", "")
        desc = result.get("description", "")
        url = result.get("url", "")
        content = f"{title} {desc}".lower()

        is_linkedin = "linkedin.com/jobs" in url
        if not is_linkedin and not any(kw in content for kw in JOB_SIGNALS):
            return None

        clean_title = (
            title.replace(" | LinkedIn", "")
            .replace(" | Indeed", "")
            .replace(" | Glassdoor", "")
            .strip()
        )

        return {
            "opportunity_type": "job",
            "title": clean_title,
            "description": desc,
            "url": url,
            "location": location,
            "company": self._extract_company(title, url),
            "matched_track": track,
            "match_score": self._score(result, track),
        }

    def parse_learning_result(
        self, result: dict[str, Any], track: str
    ) -> dict[str, Any] | None:
        title = result.get("title", "")
        desc = result.get("description", "")
        url = result.get("url", "")
        content = f"{title} {desc}".lower()

        if not any(kw in content for kw in LEARNING_SIGNALS):
            return None

        return {
            "opportunity_type": "learning",
            "title": title,
            "description": desc,
            "url": url,
            "location": "online",
            "matched_track": track,
            "match_score": self._score(result, track),
        }

    def _score(self, result: dict[str, Any], track: str) -> Decimal:
        """Deterministic relevance score 0.00–1.00."""
        score = 0.50
        content = (
            f"{result.get('title', '')} {result.get('description', '')}".lower()
        )
        keywords = self._keywords_for_track(track)
        for kw in keywords:
            if kw.lower() in content:
                score += 0.08
        return Decimal(str(min(round(score, 2), 1.0)))

    # ------------------------------------------------------------------
    # AI enrichment helpers
    # ------------------------------------------------------------------
    async def generate_networking_strategy(
        self, opportunity: dict[str, Any], user_track: str
    ) -> dict[str, Any] | None:
        """Generate a personalised networking strategy for an event.

        Returns a dict with keys: why_relevant, preparation, conversation_starters,
        goals, follow_up.  Returns None on failure.
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=600)
            messages = [
                SystemMessage(
                    content=(
                        "You are a career networking coach. Generate a concise, actionable "
                        "networking strategy for a student attending a professional event. "
                        "Reply ONLY with valid JSON (no markdown fences)."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Event: {opportunity.get('title') or ''}\n"
                        f"Description: {(opportunity.get('description') or '')[:300]}\n"
                        f"Student's track: {user_track}\n\n"
                        "Return JSON with keys: why_relevant (2 sentences), "
                        "preparation (list of 3 bullet items), "
                        "conversation_starters (list of 3 questions), "
                        "goals (string, e.g. 'Make 3 connections'), "
                        "follow_up (string, 1 sentence)"
                    )
                ),
            ]
            resp = await llm.ainvoke(messages)
            text = resp.content.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.warning("networking_strategy_generation_failed", error=str(e))
            return None

    async def generate_application_strategy(
        self, opportunity: dict[str, Any], user_track: str
    ) -> dict[str, Any] | None:
        """Generate AI application strategy for a job opportunity.

        Returns dict with keys: fit_assessment, priority, resume_points,
        cover_letter_angle, gap_mitigation, timeline.
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=600)
            messages = [
                SystemMessage(
                    content=(
                        "You are a career advisor helping a student apply for jobs. "
                        "Generate a concise application strategy. "
                        "Reply ONLY with valid JSON (no markdown fences)."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Job: {opportunity.get('title') or ''}\n"
                        f"Company: {opportunity.get('company') or 'Unknown'}\n"
                        f"Description: {(opportunity.get('description') or '')[:300]}\n"
                        f"Student's track: {user_track}\n\n"
                        "Return JSON with keys: fit_assessment (2 sentences), "
                        "priority ('immediate'|'this_week'|'low'), "
                        "resume_points (list of 3 bullet strings), "
                        "cover_letter_angle (1 sentence), "
                        "gap_mitigation (1 sentence), "
                        "timeline (string, e.g. 'Apply within 48 hours')"
                    )
                ),
            ]
            resp = await llm.ainvoke(messages)
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.warning("application_strategy_generation_failed", error=str(e))
            return None

    # ------------------------------------------------------------------
    # Core discovery flow
    # ------------------------------------------------------------------
    async def _get_tracks_for_user(
        self,
        session: AsyncSession,
        user_id: str,
        auth_token: str | None = None,
    ) -> list[str]:
        """Resolve track names for a user.

        Priority:
        1. LMS enrollments (if auth_token is a real JWT)
        2. UserPreferences.preferences JSONB (tracks / learning_track keys)
        3. Fallback: all known tracks
        """
        # 1 — Try LMS
        if auth_token and auth_token != "scheduled_job_token":
            enrollments = await self.get_user_enrollments(user_id, auth_token)
            if enrollments:
                tracks = []
                for e in enrollments:
                    course = e.get("course", {})
                    name = (
                        course.get("title")
                        or course.get("track")
                        or e.get("trackName", "")
                    )
                    if name:
                        tracks.append(name)
                if tracks:
                    logger.info("discovery_tracks_from_lms", user_id=user_id, tracks=tracks)
                    return tracks

        # 2 — Try preferences JSONB
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs and prefs.preferences:
            stored = prefs.preferences
            tracks = stored.get("tracks", []) or []
            if not tracks:
                lt = stored.get("learning_track") or stored.get("track")
                if lt:
                    tracks = [lt] if isinstance(lt, str) else list(lt)
            if tracks:
                logger.info("discovery_tracks_from_prefs", user_id=user_id, tracks=tracks)
                return tracks

        # 3 — Fallback: use all known tracks so the scheduler still produces results
        fallback = list(TRACK_KEYWORDS.keys())
        logger.warning(
            "discovery_using_fallback_tracks",
            user_id=user_id,
            reason="no LMS enrollments or stored preferences",
            tracks=fallback,
        )
        return fallback

    async def discover_for_user(
        self,
        session: AsyncSession,
        user_id: str,
        auth_token: str = "",
        search_provider: str = "auto",
        max_tracks: int = 0,
        queries_per_category: int = 3,
    ) -> list[DiscoveredOpportunity]:
        """Run full discovery pipeline for a single user.

        Args:
            session: Database session
            user_id: Authenticated user ID
            auth_token: JWT for LMS API (optional for scheduled runs)
            search_provider: 'brave', 'claude', 'both', or 'auto'
        """
        tracks = await self._get_tracks_for_user(session, user_id, auth_token)
        if not tracks:
            logger.warning("discovery_no_tracks", user_id=user_id)
            return []

        # Limit tracks if requested (e.g. scheduled job uses fewer)
        if max_tracks > 0:
            tracks = tracks[:max_tracks]

        logger.info(
            "discovery_starting",
            user_id=user_id,
            provider=search_provider,
            track_count=len(tracks),
            tracks=tracks,
        )

        location = await self.get_user_location(session, user_id) or "remote"
        logger.info("discovery_location", user_id=user_id, location=location)

        # Collect existing URLs to avoid duplicating
        existing = await session.execute(
            select(DiscoveredOpportunity.url).where(
                DiscoveredOpportunity.user_id == user_id,
                DiscoveredOpportunity.status.in_(["new", "notified"]),
            )
        )
        seen_urls: set[str] = {r[0] for r in existing.all() if r[0]}
        logger.info("discovery_existing_urls", count=len(seen_urls))

        discovered: list[DiscoveredOpportunity] = []

        for track_name in tracks:
            logger.info("discovery_processing_track", track=track_name, user_id=user_id)

            # --- Events ---
            for query in self.build_event_queries(track_name, location)[:queries_per_category]:
                logger.debug("discovery_search_query", category="event", query=query)
                search_results = await self.search(
                    query,
                    provider=search_provider,
                    freshness="pw",
                    location=location,
                )
                logger.info("discovery_search_results", category="event", query=query[:60], count=len(search_results))
                for result in search_results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    parsed = self.parse_event_result(result, track_name, location)
                    if parsed:
                        strategy = await self.generate_networking_strategy(
                            parsed, track_name
                        )
                        opp = DiscoveredOpportunity(
                            user_id=user_id,
                            opportunity_type="event",
                            title=parsed["title"],
                            description=parsed["description"],
                            url=url,
                            location=location,
                            matched_track=track_name,
                            match_score=parsed["match_score"],
                            expires_at=datetime.now(UTC) + timedelta(days=30),
                            metadata_json={
                                "source": search_provider,
                                "query": query,
                                "networking_strategy": strategy,
                            },
                        )
                        session.add(opp)
                        discovered.append(opp)

            # --- Jobs ---
            for query in self.build_job_queries(track_name, location)[:queries_per_category]:
                logger.debug("discovery_search_query", category="job", query=query)
                search_results = await self.search(
                    query,
                    provider=search_provider,
                    freshness="pw",
                    location=location,
                )
                logger.info("discovery_search_results", category="job", query=query[:60], count=len(search_results))
                for result in search_results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    parsed = self.parse_job_result(result, track_name, location)
                    if parsed:
                        strategy = await self.generate_application_strategy(
                            parsed, track_name
                        )
                        opp = DiscoveredOpportunity(
                            user_id=user_id,
                            opportunity_type="job",
                            title=parsed["title"],
                            description=parsed["description"],
                            url=url,
                            location=location,
                            company=parsed.get("company"),
                            matched_track=track_name,
                            match_score=parsed["match_score"],
                            expires_at=datetime.now(UTC) + timedelta(days=14),
                            metadata_json={
                                "source": search_provider,
                                "query": query,
                                "application_strategy": strategy,
                            },
                        )
                        session.add(opp)
                        discovered.append(opp)

            # --- Learning opportunities ---
            for query in self.build_learning_queries(track_name)[:max(1, queries_per_category - 1)]:
                logger.debug("discovery_search_query", category="learning", query=query)
                search_results = await self.search(
                    query,
                    provider=search_provider,
                    freshness="pm",
                    location=location,
                )
                logger.info("discovery_search_results", category="learning", query=query[:60], count=len(search_results))
                for result in search_results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    parsed = self.parse_learning_result(result, track_name)
                    if parsed:
                        opp = DiscoveredOpportunity(
                            user_id=user_id,
                            opportunity_type="learning",
                            title=parsed["title"],
                            description=parsed["description"],
                            url=url,
                            location="online",
                            matched_track=track_name,
                            match_score=parsed["match_score"],
                            expires_at=datetime.now(UTC) + timedelta(days=30),
                            metadata_json={
                                "source": search_provider,
                                "query": query,
                            },
                        )
                        session.add(opp)
                        discovered.append(opp)

        await session.commit()

        logger.info(
            "opportunities_discovered",
            user_id=user_id,
            total=len(discovered),
            events=len([o for o in discovered if o.opportunity_type == "event"]),
            jobs=len([o for o in discovered if o.opportunity_type == "job"]),
            learning=len(
                [o for o in discovered if o.opportunity_type == "learning"]
            ),
        )
        return discovered

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------
    async def create_opportunity_notification(
        self,
        session: AsyncSession,
        opportunity: DiscoveredOpportunity,
    ) -> Notification:
        """Create an in-app notification for a newly discovered opportunity."""
        type_label = opportunity.opportunity_type

        if type_label == "event":
            title = "🎯 New Event Matches Your Track"
            content = (
                f"We found a {opportunity.matched_track} event for you: "
                f"{opportunity.title}"
            )
            action_buttons = [
                {"action": "view", "title": "View Event", "url": opportunity.url},
                {
                    "action": "strategy",
                    "title": "Get Networking Strategy",
                    "url": f"/dashboard/opportunities?id={opportunity.id}",
                },
                {"action": "dismiss", "title": "Not Interested"},
            ]
        elif type_label == "job":
            company_part = f" at {opportunity.company}" if opportunity.company else ""
            title = "💼 Job Opportunity Alert"
            content = (
                f"New {opportunity.matched_track} role: "
                f"{opportunity.title}{company_part}"
            )
            action_buttons = [
                {"action": "view", "title": "View Job", "url": opportunity.url},
                {
                    "action": "strategy",
                    "title": "Application Strategy",
                    "url": f"/dashboard/opportunities?id={opportunity.id}",
                },
                {"action": "dismiss", "title": "Not Interested"},
            ]
        else:
            title = "🎓 Learning Opportunity"
            content = (
                f"Free resource for your {opportunity.matched_track} journey: "
                f"{opportunity.title}"
            )
            action_buttons = [
                {"action": "view", "title": "Check It Out", "url": opportunity.url},
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
                "url": opportunity.url,
            },
            expires_at=opportunity.expires_at,
        )
        session.add(notification)
        opportunity.status = "notified"
        await session.commit()
        return notification


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
opportunity_engine = OpportunityDiscoveryEngine()
