"""Authentication dependencies for FastAPI endpoints"""

from typing import Any

from fastapi import Depends, HTTPException, Request

from ..models.auth import User


def _extract_user_data(user_obj: Any) -> dict[str, Any]:
    """Extract user data from various object types.

    Handles dict, objects with to_dict(), and objects with dict() methods.

    Args:
        user_obj: User object from authentication middleware

    Returns:
        Dictionary containing user data
    """
    if isinstance(user_obj, dict):
        return user_obj
    if hasattr(user_obj, "to_dict"):
        return user_obj.to_dict()
    if hasattr(user_obj, "dict"):
        return user_obj.dict()
    # Fallback: try to extract known attributes
    return {
        "identity": getattr(user_obj, "identity", str(user_obj)),
        "is_authenticated": getattr(user_obj, "is_authenticated", True),
    }


def get_current_user(request: Request) -> User:
    """
    Extract current user from request context set by authentication middleware.

    The authentication middleware sets request.user after calling our
    LangGraph auth handlers (@auth.authenticate).

    This function passes ALL fields from auth handlers through to the User model,
    allowing custom auth handlers to return extra fields (e.g., subscription_tier,
    team_id) that will be accessible on the User object.

    Args:
        request: FastAPI request object

    Returns:
        User object with authentication context including any extra fields

    Raises:
        HTTPException: If user is not authenticated
    """
    # Get user from Starlette authentication middleware
    if not hasattr(request, "user") or request.user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not request.user.is_authenticated:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Extract user data from various object types
    user_data = _extract_user_data(request.user)

    # Ensure identity exists
    if "identity" not in user_data:
        raise HTTPException(status_code=401, detail="User identity not provided")

    # Set display_name default if not provided
    if user_data.get("display_name") is None:
        user_data["display_name"] = user_data["identity"]

    # Pass all fields through to User model (extra fields allowed via ConfigDict)
    return User(**user_data)


def get_user_id(user: User = Depends(get_current_user)) -> str:
    """
    Helper dependency to get user ID safely.

    Args:
        user: User object from get_current_user dependency

    Returns:
        User identity string
    """
    return user.identity


def require_permission(permission: str):
    """
    Create a dependency that requires a specific permission.

    Args:
        permission: Required permission string

    Returns:
        Dependency function that checks for the permission

    Example:
        @app.get("/admin")
        def admin_endpoint(user: User = Depends(require_permission("admin"))):
            return {"message": "Admin access granted"}
    """

    def permission_dependency(user: User = Depends(get_current_user)) -> User:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=403, detail=f"Permission '{permission}' required"
            )
        return user

    return permission_dependency


def require_authenticated(request: Request) -> User:
    """
    Simplified dependency that just ensures user is authenticated.

    This is equivalent to get_current_user but with a clearer name
    for endpoints that just need any authenticated user.
    """
    return get_current_user(request)
