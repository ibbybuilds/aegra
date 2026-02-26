"""MCP factory example — async context manager for MCP server lifecycle.

The factory returns an async context manager that keeps the MCP server
connection alive for the duration of graph execution. When the graph
finishes, the connection is cleanly torn down.

Requires ``langchain-mcp-adapters`` to be installed::

    pip install langchain-mcp-adapters

Usage in aegra.json::

    {
      "graphs": {
        "mcp_factory": "./examples/factory_mcp/graph.py:graph"
      }
    }
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph_sdk.runtime import ServerRuntime

from factory_mcp.utils import load_chat_model

# ---------------------------------------------------------------------------
# MCP server configuration
# ---------------------------------------------------------------------------

MCP_SERVERS: dict[str, dict[str, Any]] = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],  # nosec B108
        "transport": "stdio",
    },
    # Add more MCP servers here:
    # "github": {
    #     "command": "npx",
    #     "args": ["-y", "@modelcontextprotocol/server-github"],
    #     "transport": "stdio",
    #     "env": {"GITHUB_TOKEN": "..."},
    # },
}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def graph(runtime: ServerRuntime) -> AsyncIterator[Any]:
    """MCP factory — async context manager that manages MCP server lifecycle.

    The MCP client connection is established when the graph is requested
    and torn down when execution completes. Tools from all configured MCP
    servers are automatically discovered and bound to the agent.

    Args:
        runtime: The server runtime with user, store, and access context.

    Yields:
        A compiled ReAct agent with MCP tools bound.
    """
    model = load_chat_model("openai/gpt-4o-mini")

    async with MultiServerMCPClient(MCP_SERVERS) as mcp_client:
        tools = mcp_client.get_tools()

        agent = create_react_agent(
            model,
            tools,
            name="MCP Factory Agent",
        )

        yield agent
