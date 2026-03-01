"""Unified factory example — typed context, user-aware tools, and MCP lifecycle.

Demonstrates all factory capabilities in a single graph:

- **Model selection** via ``FactoryContext.model``
- **System prompt** via ``FactoryContext.system_prompt``
- **Graph structure changes** via ``FactoryContext.enable_search`` (conditionally
  includes/excludes the ``search_web`` tool and the ``tools`` node)
- **User-aware tool filtering** via ``runtime.user`` (admin users get
  ``delete_user``)
- **MCP lifecycle** via ``FactoryContext.enable_mcp`` (async context manager
  spins up MCP tool servers when enabled)

Usage in aegra.json::

    {
      "graphs": {
        "factory": "./examples/factory/graph.py:graph"
      }
    }
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph_sdk.runtime import ServerRuntime
from typing_extensions import TypedDict

from factory.context import FactoryContext
from factory.tools import get_tools
from factory.utils import load_chat_model

# Optional MCP dependency — the example works without it
try:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

# ---------------------------------------------------------------------------
# MCP server configuration (used when enable_mcp=True)
# ---------------------------------------------------------------------------

MCP_SERVERS: dict[str, dict[str, Any]] = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],  # nosec B108
        "transport": "stdio",
    },
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State(TypedDict):
    """Minimal chat state."""

    messages: list[AnyMessage]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def _build_graph(ctx: FactoryContext, tools: list[BaseTool]) -> Any:
    """Build and compile the graph, adapting structure to the tool list.

    When *tools* is non-empty the graph includes a ``tools`` node and a
    conditional edge from ``call_model`` that routes tool-call responses
    to it. When *tools* is empty, the graph is a simple
    ``__start__ -> call_model -> __end__`` chain.
    """
    system_msg = ctx.system_prompt

    async def call_model(state: State, config: RunnableConfig) -> dict[str, list[AIMessage]]:
        """Call the LLM, optionally binding tools."""
        model = load_chat_model(ctx.model)

        if tools:
            model = model.bind_tools(tools)

        existing = list(state.get("messages", []))
        if existing and isinstance(existing[0], SystemMessage) and existing[0].content == system_msg:
            messages = existing
        else:
            messages = [SystemMessage(content=system_msg), *existing]

        response = cast("AIMessage", await model.ainvoke(messages))
        return {"messages": [response]}

    builder = StateGraph(State)
    builder.add_node("call_model", call_model)
    builder.add_edge("__start__", "call_model")

    if tools:

        def route_output(state: State) -> Literal["__end__", "tools"]:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "tools"
            return "__end__"

        builder.add_node("tools", ToolNode(tools))
        builder.add_conditional_edges("call_model", route_output)
        builder.add_edge("tools", "call_model")
    else:
        builder.add_edge("call_model", "__end__")

    return builder.compile(name="Factory Agent")


# ---------------------------------------------------------------------------
# Factory entry point
# ---------------------------------------------------------------------------


@asynccontextmanager
async def graph(config: dict[str, Any], runtime: ServerRuntime[FactoryContext]) -> AsyncIterator[Any]:
    """Unified factory — 2-param async context manager.

    Accepts both ``config`` (RunnableConfig dict) and ``runtime``
    (``ServerRuntime[FactoryContext]``). The ``FactoryContext`` is read from
    ``runtime.execution_runtime.context`` during run execution; for
    non-execution contexts (schema extraction, graph visualisation) defaults
    are used.

    The async context manager form allows MCP server connections to be
    established on entry and torn down on exit.
    """
    ert = runtime.execution_runtime
    if ert:
        ctx = ert.context or FactoryContext()
    else:
        ctx = FactoryContext()

    # Assemble tools based on context + user permissions
    tools = list(get_tools(ctx, runtime.user))

    # Optionally add MCP tools (only in execution context)
    mcp_client = None
    if ctx.enable_mcp and ert and _HAS_MCP:
        client = MultiServerMCPClient(MCP_SERVERS)
        await client.__aenter__()
        mcp_client = client  # only set after successful entry
        mcp_tools: list[BaseTool] = mcp_client.get_tools()
        tools.extend(mcp_tools)

    compiled = _build_graph(ctx, tools)

    try:
        yield compiled
    finally:
        if mcp_client is not None:
            await mcp_client.__aexit__(None, None, None)
