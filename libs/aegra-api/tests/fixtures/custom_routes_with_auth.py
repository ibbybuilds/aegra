"""Custom routes for testing authentication flow.

These routes test:
1. User data extraction from auth dependency
2. Custom fields preservation
3. Auth dependency application to custom routes
"""

from fastapi import Depends, FastAPI, Request

from aegra_api.core.auth_deps import require_auth
from aegra_api.models.auth import User

app = FastAPI(
    title="Auth Test Routes",
    description="Custom endpoints for testing authentication flow",
)


@app.get("/custom/whoami")
async def whoami(request: Request, user: User = Depends(require_auth)):
    """Return current user info - tests that auth flows to custom routes.

    This endpoint explicitly uses get_current_user dependency to test
    that authentication works correctly with custom routes.
    """
    return {
        "identity": user.identity,
        "display_name": user.display_name,
        "is_authenticated": user.is_authenticated,
        "permissions": user.permissions,
        # Custom fields that should be accessible
        "role": getattr(user, "role", None),
        "subscription_tier": getattr(user, "subscription_tier", None),
        "team_id": getattr(user, "team_id", None),
        "email": getattr(user, "email", None),
    }


@app.get("/custom/public")
async def public_endpoint():
    """Public endpoint - no auth dependency explicitly added.

    This endpoint will be protected if enable_custom_route_auth is True,
    otherwise it will be public.
    """
    return {
        "message": "This is public by default",
        "note": "Protected if enable_custom_route_auth is enabled",
    }


@app.get("/custom/protected")
async def protected_endpoint(user: User = Depends(require_auth)):
    """Protected endpoint - explicitly requires auth dependency.

    This endpoint always requires authentication regardless of config.
    """
    return {
        "message": "This endpoint is always protected",
        "user": user.identity,
        "role": getattr(user, "role", None),
    }
