"""Authentication and user context models"""

from pydantic import BaseModel


class User(BaseModel):
    """User context model for authentication"""

    identity: str
    display_name: str | None = None
    permissions: list[str] = []
    org_id: str | None = None
    is_authenticated: bool = True


class AuthContext(BaseModel):
    """Authentication context for request processing"""

    user: User
    request_id: str | None = None

    class Config:
        arbitrary_types_allowed = True


class TokenPayload(BaseModel):
    """JWT token payload structure"""

    sub: str  # subject (user ID)
    name: str | None = None
    scopes: list[str] = []
    org: str | None = None
    exp: int | None = None
    iat: int | None = None
