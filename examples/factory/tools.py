"""Tool definitions and permission-aware tool assembly."""

from langchain_core.tools import BaseTool, tool
from langgraph_sdk.auth.types import BaseUser

from factory.context import FactoryContext

# ---------------------------------------------------------------------------
# Tool stubs
# ---------------------------------------------------------------------------


@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


@tool
def delete_user(user_id: str) -> str:
    """Delete a user account. Admin only."""
    return f"User {user_id} deleted."


# ---------------------------------------------------------------------------
# Tool assembly
# ---------------------------------------------------------------------------


def get_tools(ctx: FactoryContext, user: BaseUser | None) -> list[BaseTool]:
    """Assemble the tool list based on context flags and user permissions.

    Args:
        ctx: The factory context controlling which features are enabled.
        user: The authenticated user (or ``None`` for anonymous access).

    Returns:
        A list of tools the agent should have access to.
    """
    tools: list[BaseTool] = []

    if ctx.enable_search:
        tools.append(search_web)

    # Admin-only tools
    is_admin = False
    if user is not None:
        permissions = getattr(user, "permissions", []) or []
        is_admin = "admin" in permissions

    if is_admin:
        tools.append(delete_user)

    return tools
