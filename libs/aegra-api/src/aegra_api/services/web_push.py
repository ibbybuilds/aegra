"""Web Push Notification Service.

Sends real push notifications via the Web Push Protocol (RFC 8030)
using VAPID authentication so users receive notifications even when
the browser tab is closed.

Requirements:
- pywebpush
- VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY env vars (generate once, keep stable)
- Clients subscribe via the Push API and store their subscription on the server

Generate VAPID keys once:
    python -c "from pywebpush import webpush; from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('public:', v.public_key); print('private:', v.private_key)"
Or use: npx web-push generate-vapid-keys
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.accountability_orm import UserPreferences
from aegra_api.settings import settings

logger = structlog.get_logger()


class WebPushService:
    """Manages Web Push subscriptions and message delivery."""

    def __init__(self) -> None:
        self.vapid_public_key = settings.push.VAPID_PUBLIC_KEY
        self.vapid_private_key = settings.push.VAPID_PRIVATE_KEY
        self.vapid_claims = {"sub": settings.push.VAPID_CLAIMS_EMAIL}

    @property
    def is_configured(self) -> bool:
        """Return True if VAPID keys are set."""
        return bool(self.vapid_public_key and self.vapid_private_key)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------
    async def save_subscription(
        self,
        session: AsyncSession,
        user_id: str,
        subscription_info: dict[str, Any],
    ) -> None:
        """Persist a push subscription for a user.

        subscription_info should contain: endpoint, keys.p256dh, keys.auth
        """
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = UserPreferences(user_id=user_id)
            session.add(prefs)

        prefs.push_subscription = subscription_info
        await session.commit()

        logger.info(
            "push_subscription_saved",
            user_id=user_id,
            endpoint=subscription_info.get("endpoint", "")[:60],
        )

    async def remove_subscription(
        self, session: AsyncSession, user_id: str
    ) -> None:
        """Remove push subscription for a user."""
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs:
            prefs.push_subscription = None
            await session.commit()

        logger.info("push_subscription_removed", user_id=user_id)

    async def get_subscription(
        self, session: AsyncSession, user_id: str
    ) -> dict[str, Any] | None:
        """Get the stored push subscription for a user."""
        result = await session.execute(
            select(UserPreferences.push_subscription).where(
                UserPreferences.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Push delivery
    # ------------------------------------------------------------------
    async def send_push(
        self,
        subscription_info: dict[str, Any],
        payload: dict[str, Any],
    ) -> bool:
        """Send a web push notification to a single subscription.

        Args:
            subscription_info: PushSubscription JSON (endpoint, keys)
            payload: Notification data (title, body, icon, url, etc.)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.warning("VAPID keys not configured — cannot send web push")
            return False

        try:
            from pywebpush import webpush

            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=self.vapid_claims,
                ttl=86400,  # 24 hours
            )
            logger.info(
                "web_push_sent",
                endpoint=subscription_info.get("endpoint", "")[:60],
                title=payload.get("title", ""),
            )
            return True

        except Exception as e:
            error_str = str(e)
            # Handle expired/invalid subscriptions (410 Gone, 404)
            if "410" in error_str or "404" in error_str:
                logger.warning(
                    "push_subscription_expired",
                    endpoint=subscription_info.get("endpoint", "")[:60],
                )
            else:
                logger.error("web_push_failed", error=error_str)
            return False

    async def send_to_user(
        self,
        session: AsyncSession,
        user_id: str,
        payload: dict[str, Any],
    ) -> bool:
        """Send a web push to a specific user if they have a subscription.

        Automatically cleans up expired subscriptions.
        """
        subscription = await self.get_subscription(session, user_id)
        if not subscription:
            return False

        success = await self.send_push(subscription, payload)

        # Clean up expired subscriptions
        if not success:
            await self.remove_subscription(session, user_id)

        return success

    def build_payload(
        self,
        title: str,
        body: str,
        *,
        category: str = "general",
        priority: str = "normal",
        url: str | None = None,
        notification_id: str | None = None,
        icon: str = "/icons/dedatahub-icon.png",
        badge: str = "/icons/badge.png",
    ) -> dict[str, Any]:
        """Build a standard push notification payload.

        The Service Worker on the client will read these fields.
        """
        return {
            "title": title,
            "body": body,
            "icon": icon,
            "badge": badge,
            "tag": notification_id or category,
            "data": {
                "url": url or "/dashboard",
                "category": category,
                "priority": priority,
                "notificationId": notification_id,
            },
            "requireInteraction": priority in ("urgent", "critical"),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
web_push_service = WebPushService()
