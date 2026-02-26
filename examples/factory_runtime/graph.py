"""Runtime factory example — user-aware agent with per-user tool access.

The factory receives a ``ServerRuntime`` on every invocation, providing
access to the authenticated user, the persistence store, and the access
context (why the factory is being called).

Usage in aegra.json::

    {
      "graphs": {
        "runtime_factory": "./examples/factory_runtime/graph.py:graph"
      }
    }
"""

from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph_sdk.runtime import ServerRuntime

from factory_runtime.utils import load_chat_model

# ---------------------------------------------------------------------------
# Tools — some are admin-only
# ---------------------------------------------------------------------------


@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


@tool
def delete_user(user_id: str) -> str:
    """Delete a user account. Admin only."""
    return f"User {user_id} deleted."


ALL_TOOLS = [search_web, delete_user]
PUBLIC_TOOLS = [search_web]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def call_model(state: dict[str, Any], config: dict[str, Any]) -> dict[str, list]:
    """Call the LLM with tools available to the current user."""
    model = load_chat_model("openai/gpt-4o-mini")
    tools = state.get("_tools", PUBLIC_TOOLS)
    bound = model.bind_tools(tools)

    response = cast(
        "AIMessage",
        await bound.ainvoke(state["messages"]),
    )
    return {"messages": [response]}


def route_output(state: dict[str, Any]) -> Literal["__end__", "tools"]:
    """Route to tools or end."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "__end__"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def graph(runtime: ServerRuntime) -> Any:
    """Runtime factory — called per-request with user context.

    Grants admin users access to privileged tools (e.g. ``delete_user``).
    Regular users only get public tools.

    The ``runtime.user`` object comes from your auth handler. If auth is
    disabled, ``runtime.user`` is ``None``.
    """
    # Determine tools based on user permissions
    user = runtime.user
    is_admin = False
    if user is not None:
        permissions = getattr(user, "permissions", [])
        is_admin = "admin" in permissions

    tools = ALL_TOOLS if is_admin else PUBLIC_TOOLS

    # Build a greeting based on user identity
    user_name = getattr(user, "display_name", None) or "there"
    system_msg = f"You are a helpful assistant. Hello {user_name}!"
    if is_admin:
        system_msg += " You have admin privileges."

    builder = StateGraph(dict)

    # Inject tools into state so call_model can use them
    def inject_context(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "_tools": tools,
            "messages": [SystemMessage(content=system_msg), *state.get("messages", [])],
        }

    builder.add_node("inject", inject_context)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge("__start__", "inject")
    builder.add_edge("inject", "call_model")
    builder.add_conditional_edges("call_model", route_output)
    builder.add_edge("tools", "call_model")

    return builder.compile(name="Runtime Factory Agent")
