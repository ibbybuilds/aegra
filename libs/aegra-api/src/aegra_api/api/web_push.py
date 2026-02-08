"""API endpoints for Web Push subscription management.

Endpoints:
- GET   /push/vapid-key     returns the VAPID public key for client-side Push API
- POST  /push/subscribe     save a push subscription
- POST  /push/unsubscribe   remove a push subscription
- POST  /push/test          send a test push notification
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.auth_deps import get_current_user
from aegra_api.core.orm import get_session
from aegra_api.models import User
from aegra_api.services.web_push import web_push_service

router = APIRouter(prefix="/push", tags=["Web Push"])


# ── Models ───────────────────────────────────────────────────────────

class PushSubscriptionRequest(BaseModel):
    """Standard PushSubscription JSON from browser Push API."""
    endpoint: str
    keys: dict[str, str]  # p256dh, auth
    expirationTime: int | None = None


# ── VAPID Public Key ─────────────────────────────────────────────────

@router.get("/vapid-key")
async def get_vapid_key() -> dict[str, Any]:
    """Return the VAPID application server public key.

    The client uses this to subscribe to push notifications.
    """
    return {
        "publicKey": web_push_service.vapid_public_key or "",
        "configured": web_push_service.is_configured,
    }


# ── Subscribe ────────────────────────────────────────────────────────

@router.post("/subscribe")
async def subscribe(
    body: PushSubscriptionRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Save a push subscription for the authenticated user.

    The client calls this after successfully calling
    `pushManager.subscribe()` in the browser.
    """
    subscription_info = {
        "endpoint": body.endpoint,
        "keys": body.keys,
    }
    if body.expirationTime is not None:
        subscription_info["expirationTime"] = body.expirationTime

    await web_push_service.save_subscription(
        session, user.identity, subscription_info
    )
    return {"status": "subscribed"}


# ── Unsubscribe ──────────────────────────────────────────────────────

@router.post("/unsubscribe")
async def unsubscribe(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Remove the push subscription for the authenticated user."""
    await web_push_service.remove_subscription(session, user.identity)
    return {"status": "unsubscribed"}


# ── Test Push ────────────────────────────────────────────────────────

@router.post("/test")
async def test_push(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a test push notification to the current user."""
    payload = web_push_service.build_payload(
        title="🔔 DeDataHub Push Test",
        body="Push notifications are working! You'll receive alerts even when the browser is closed.",
        category="general",
        url="/dashboard",
    )
    sent = await web_push_service.send_to_user(session, user.identity, payload)
    return {
        "status": "sent" if sent else "no_subscription",
        "message": (
            "Test notification sent!"
            if sent
            else "No push subscription found. Enable push notifications first."
        ),
    }
