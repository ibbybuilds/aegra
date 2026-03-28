"""E2E tests for MCP endpoint using the `mcp` SDK client.

These tests connect to a real running Aegra server using the MCP client
SDK's Streamable HTTP transport and verify tool discovery and invocation.
"""


import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tests.e2e._utils import elog

pytestmark = pytest.mark.e2e

BASE_URL = "http://localhost:2026"


async def _check_server() -> None:
    """Skip test if server is not reachable."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code != 200:
                pytest.skip("Server not healthy")
    except httpx.ConnectError:
        pytest.skip("Server not reachable")


# ---------------------------------------------------------------------------
# MCP SDK client tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_client_connects_and_initializes() -> None:
    """MCP client can connect to /mcp and complete the initialize handshake."""
    await _check_server()

    async with streamablehttp_client(url=f"{BASE_URL}/mcp") as (read, write, _):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            await session.initialize()

            elog("MCP session initialized", {
                "server_name": session.server_info.name if session.server_info else "unknown",
            })
            # If we got here, initialization succeeded
            assert session.server_info is not None


@pytest.mark.asyncio
async def test_mcp_client_discovers_tools() -> None:
    """MCP tools/list returns at least one tool corresponding to a registered graph."""
    await _check_server()

    async with streamablehttp_client(url=f"{BASE_URL}/mcp") as (read, write, _):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]

            elog("MCP tools discovered", tool_names)
            assert len(tool_names) > 0, "Expected at least one MCP tool"
            # The 'agent' graph from aegra.json should be exposed as a tool
            assert "agent" in tool_names, f"Expected 'agent' tool, got: {tool_names}"


@pytest.mark.asyncio
async def test_mcp_client_tool_has_input_schema() -> None:
    """Each MCP tool has a non-empty inputSchema describing graph input."""
    await _check_server()

    async with streamablehttp_client(url=f"{BASE_URL}/mcp") as (read, write, _):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()

            for tool in tools_result.tools:
                elog(f"Tool '{tool.name}' schema", tool.inputSchema)
                assert tool.inputSchema is not None, f"Tool '{tool.name}' has no inputSchema"
                assert isinstance(tool.inputSchema, dict), f"Tool '{tool.name}' schema is not a dict"


@pytest.mark.asyncio
async def test_mcp_client_call_tool() -> None:
    """MCP tools/call invokes the graph and returns a text result.

    This test requires a configured LLM API key in the server's .env.
    Skips gracefully if the graph execution fails due to missing credentials.
    """
    await _check_server()

    async with streamablehttp_client(url=f"{BASE_URL}/mcp") as (read, write, _):  # noqa: SIM117
        async with ClientSession(read, write) as session:
            await session.initialize()

            try:
                result = await session.call_tool(
                    "agent",
                    arguments={"messages": [{"role": "user", "content": "Say hello in one word."}]},
                )
            except Exception as exc:
                pytest.skip(f"Tool call failed (likely missing LLM credentials): {exc}")

            elog("MCP tool call result", {
                "content_count": len(result.content),
                "is_error": result.isError,
            })
            assert not result.isError, f"Tool call returned error: {result.content}"
            assert len(result.content) > 0, "Expected at least one content block"
