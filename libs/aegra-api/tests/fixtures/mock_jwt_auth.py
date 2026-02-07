"""Mock JWT authentication handler for testing.

This simulates a real JWT authentication system that validates tokens
and returns user data with custom fields. Also includes authorization handlers
to demonstrate @auth.on.* functionality.

Token format: mock-jwt-<user_id>-<role>-<extra_data>
Example: mock-jwt-alice-admin-team123
"""

from langgraph_sdk import Auth

auth = Auth()


@auth.authenticate
async def authenticate(headers: dict) -> dict:
    """Mock JWT authentication that simulates real JWT behavior.

    Expects: Authorization: Bearer <token>
    Token format: mock-jwt-<user_id>-<role>-<extra_data>

    Returns user data with custom fields that should flow through to routes.

    Args:
        headers: Request headers dict

    Returns:
        User data dict with identity, display_name, permissions, and custom fields

    Raises:
        HTTPException: If token is missing or invalid
    """
    auth_header = headers.get("authorization", "") or headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]  # Strip "Bearer "

    # Parse mock token: mock-jwt-userid-role-extra
    if not token.startswith("mock-jwt-"):
        raise Auth.exceptions.HTTPException(status_code=401, detail="Invalid token format")

    parts = token.split("-")[2:]  # Skip "mock-jwt"
    if len(parts) < 2:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Token missing required fields")

    user_id = parts[0]
    role = parts[1]
    team_id = parts[2] if len(parts) > 2 else "team_default"

    # Determine subscription tier based on role
    subscription_tier = "premium" if role in ("admin", "premium") else "free"

    return {
        "identity": user_id,
        "display_name": f"User {user_id}",
        "is_authenticated": True,
        "permissions": [role, f"{role}:read", f"{role}:write"],
        # Custom fields that should flow through to User model
        "role": role,
        "subscription_tier": subscription_tier,
        "team_id": team_id,
        "email": f"{user_id}@example.com",
    }


# Authorization handlers


# Global fallback handler - runs for all resources/actions that don't have specific handlers
@auth.on
async def authorize(ctx, value):
    """Global authorization handler - fallback for all requests."""
    # Default behavior: allow but don't apply filters
    # Specific handlers will override this
    return True


@auth.on.threads.create
async def allow_thread_create(ctx, value):
    """Allow thread creation and inject team_id into metadata"""
    # Ensure metadata exists (handle None case)
    if value.get("metadata") is None:
        value["metadata"] = {}
    # Inject team_id from user custom fields
    try:
        team_id = ctx.user["team_id"] if "team_id" in ctx.user else getattr(ctx.user, "team_id", None)
        if team_id:
            value["metadata"]["team_id"] = team_id
    except (KeyError, AttributeError):
        pass
    return True


@auth.on.threads.search
async def filter_threads_by_team(ctx, value):
    """Filter thread searches by team_id"""
    try:
        team_id = ctx.user["team_id"] if "team_id" in ctx.user else getattr(ctx.user, "team_id", None)
        if team_id:
            return {"metadata": {"team_id": team_id}}
    except (KeyError, AttributeError):
        pass
    return {"user_id": ctx.user.identity}


@auth.on.assistants.delete
async def restrict_assistant_deletion(ctx, value):
    """Only admins can delete assistants"""
    try:
        role = ctx.user["role"] if "role" in ctx.user else getattr(ctx.user, "role", None)
        if role == "admin":
            return True
    except (KeyError, AttributeError):
        pass
    return False


@auth.on.assistants.create
async def allow_assistant_create(ctx, value):
    """Allow assistant creation and inject creator info"""
    # Ensure metadata exists (handle None case)
    if value.get("metadata") is None:
        value["metadata"] = {}
    value["metadata"]["created_by"] = ctx.user.identity
    try:
        team_id = ctx.user["team_id"] if "team_id" in ctx.user else getattr(ctx.user, "team_id", None)
        if team_id:
            value["metadata"]["team_id"] = team_id
    except (KeyError, AttributeError):
        pass
    return True
