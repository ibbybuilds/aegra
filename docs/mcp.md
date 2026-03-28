# MCP (Model Context Protocol)

Aegra exposes all configured graphs as MCP tools via the [Model Context Protocol](https://modelcontextprotocol.io/). This lets you use your deployed agents as tools in Claude Desktop, Cursor, and any other MCP-compatible client.

## Overview

When Aegra starts, it automatically creates one MCP tool per graph defined in `aegra.json`. The tool name matches the `graph_id`, and the input schema is auto-discovered from the graph's input schema.

Each tool invocation runs the agent and returns its output. The transport is Streamable HTTP, which supports both request/response and streaming interactions.

## Endpoint

```
POST /mcp
```

Aegra exposes a single Streamable HTTP endpoint at `/mcp`. All MCP interactions go through this endpoint using the standard MCP JSON-RPC protocol over HTTP.

## Connecting from Claude Desktop

Add the following to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "aegra": {
      "url": "http://localhost:2026/mcp",
      "transport": "streamable-http"
    }
  }
}
```

After restarting Claude Desktop, your Aegra agents will appear as available tools.

## Connecting from Python

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async with streamablehttp_client(url="http://localhost:2026/mcp") as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print(tools)
```

## Tool discovery

Each graph becomes one MCP tool:

- **Tool name**: the `graph_id` from `aegra.json` (e.g., `"agent"`, `"assistant"`)
- **Input schema**: auto-derived from the graph's input schema
- **Description**: the graph's description if set, otherwise a default description

For example, if `aegra.json` defines:

```json
{
  "graphs": {
    "agent": "./src/agent/graph.py:graph",
    "researcher": "./src/researcher/graph.py:graph"
  }
}
```

Then two MCP tools are exposed: `agent` and `researcher`.

## Authentication

MCP uses the same authentication as the rest of Aegra. If you have an `auth` handler configured in `aegra.json`, all MCP requests go through it.

For Claude Desktop and other clients that support HTTP headers, pass your token in the `Authorization` header:

```json
{
  "mcpServers": {
    "aegra": {
      "url": "http://localhost:2026/mcp",
      "transport": "streamable-http",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

If no auth is configured, all MCP requests are allowed.

## Stateless operation

The MCP endpoint is stateless. Each tool call is an independent request — there are no persistent sessions. State between calls is not maintained at the MCP layer. If you need persistent conversation state, use the Agent Protocol (`/threads` and `/runs`) directly.

## Configuration

MCP is enabled by default. To disable it, set `disable_mcp` in the `http` section of `aegra.json`:

```json
{
  "graphs": {
    "agent": "./src/agent/graph.py:graph"
  },
  "http": {
    "disable_mcp": true
  }
}
```

See the [configuration reference](/reference/configuration) for all `http` options.
