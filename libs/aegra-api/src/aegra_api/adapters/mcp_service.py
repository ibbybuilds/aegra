"""MCP service layer.

Maps MCP tool calls to Agent Protocol runs. Each graph in the registry
becomes a callable MCP tool. Tool execution delegates to the existing
``stateless_wait_for_run`` function, which handles ephemeral thread
creation, graph execution, waiting for output, and cleanup.
"""

from typing import Any

import structlog

from aegra_api.api.stateless_runs import stateless_wait_for_run
from aegra_api.models import RunCreate, User
from aegra_api.utils.assistants import resolve_assistant_id

logger = structlog.get_logger(__name__)


class MCPService:
    """Service that exposes graphs as MCP tools.

    Provides ``list_tools`` for schema discovery and ``call_tool`` for
    execution. Each graph in the registry becomes one MCP tool.
    """

    def __init__(self) -> None:
        self._langgraph_service: Any = None

    def set_langgraph_service(self, service: Any) -> None:
        """Inject the LangGraphService dependency.

        Args:
            service: A configured ``LangGraphService`` instance.
        """
        self._langgraph_service = service

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return one MCP tool descriptor per registered graph.

        Retrieves the input JSON schema from each graph's compiled base
        definition. Graphs that fail to load are skipped with a warning.

        Returns:
            List of tool descriptor dicts with ``name``, ``description``,
            and ``inputSchema`` keys.
        """
        tools: list[dict[str, Any]] = []
        registry: dict[str, Any] = self._langgraph_service._graph_registry

        for graph_id in registry:
            try:
                graph = await self._langgraph_service._get_base_graph(graph_id)
                input_schema = graph.get_input_jsonschema()
            except Exception:
                logger.exception("mcp_list_tools_graph_load_failed", graph_id=graph_id)
                continue

            tools.append(
                {
                    "name": graph_id,
                    "description": f"Run the {graph_id} agent",
                    "inputSchema": input_schema,
                }
            )

        return tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any], user: User,
    ) -> dict[str, Any]:
        """Execute a graph as an MCP tool call.

        Delegates to ``stateless_wait_for_run`` from the stateless runs
        API, which creates an ephemeral thread, runs the graph, waits
        for output, and cleans up the thread automatically.

        Args:
            tool_name: The graph ID (tool name) to invoke.
            arguments: Input arguments forwarded to the graph.
            user: The authenticated user making the request.

        Returns:
            The final output dict from the graph run.

        Raises:
            ValueError: If ``tool_name`` is not a known graph ID.
        """
        registry: dict[str, Any] = self._langgraph_service._graph_registry

        if tool_name not in registry:
            raise ValueError(f"Unknown tool: {tool_name!r}")

        assistant_id = resolve_assistant_id(tool_name, registry)

        request = RunCreate(
            assistant_id=assistant_id,
            input=arguments,
        )

        return await stateless_wait_for_run(request, user)


# Global service instance
_mcp_service: MCPService | None = None


def get_mcp_service() -> MCPService:
    """Return the global MCPService instance."""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPService()
    return _mcp_service
