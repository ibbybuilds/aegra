"""Authentication dependencies for FastAPI endpoints"""

from fastapi import Depends, HTTPException, Request

from ..models.auth import User


def get_current_user(request: Request) -> User:
    """
    Extract current user from request context set by authentication middleware.

    The authentication middleware sets request.user after calling our
    LangGraph auth handlers (@auth.authenticate).

    Args:
        request: FastAPI request object

    Returns:
        User object with authentication context

    Raises:
        HTTPException: If user is not authenticated
    """

    # Get user from Starlette authentication middleware
    if not hasattr(request, "user") or request.user is None:
        # No authentication middleware or user not set
        raise HTTPException(status_code=401, detail="Authentication required")

    if not request.user.is_authenticated:
        # User is explicitly not authenticated
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Convert LangGraphUser to our User model
    # request.user is the LangGraphUser instance from auth_middleware
    user_data = request.user.to_dict()

    return User(
        identity=user_data["identity"],
        display_name=user_data.get("display_name"),
        permissions=user_data.get("permissions", []),
        org_id=user_data.get("org_id"),
        is_authenticated=user_data.get("is_authenticated", True),
    )


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
