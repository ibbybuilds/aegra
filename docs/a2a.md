# A2A (Agent-to-Agent) Protocol

Aegra implements the [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/), which allows other agents and systems to discover and communicate with your Aegra agents using a standard, interoperable interface.

## Overview

A2A is a JSON-RPC 2.0 protocol that defines a standard way for agents to exchange messages, manage tasks, and discover each other's capabilities. Aegra exposes each assistant via A2A, enabling multi-agent workflows where your agents can be orchestrated by external systems.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/a2a/{assistant_id}` | POST | JSON-RPC endpoint for a specific assistant |
| `/.well-known/agent-card.json` | GET | Agent card discovery (default assistant) |
| `/a2a/agent-cards` | GET | List all agent cards |

## Agent card discovery

Agent cards describe an agent's capabilities and how to interact with it. Use the well-known URL for discovery:

```bash
curl http://localhost:2026/.well-known/agent-card.json
```

To list all agents:

```bash
curl http://localhost:2026/a2a/agent-cards
```

## Sending a message

Use `message/send` to send a message to an agent and receive a response:

```bash
curl -X POST http://localhost:2026/a2a/agent \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [{"kind": "text", "text": "Hello"}]
      }
    }
  }'
```

## Streaming

Use `message/stream` to receive Server-Sent Events as the agent processes your message:

```bash
curl -N -X POST http://localhost:2026/a2a/agent \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/stream",
    "params": {
      "message": {
        "messageId": "msg-2",
        "role": "user",
        "parts": [{"kind": "text", "text": "Hello"}]
      }
    }
  }'
```

The stream emits `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` objects as the agent runs.

## Supported JSON-RPC methods

| Method | Description |
|--------|-------------|
| `message/send` | Send a message and get a complete response |
| `message/stream` | Send a message and stream the response via SSE |
| `tasks/get` | Retrieve the status and result of a task |
| `tasks/cancel` | Cancel an in-progress task |

## Task lifecycle

A2A tasks map directly to Aegra's thread and run system:

- **`contextId`** maps to a `thread_id` — represents the ongoing conversation context
- **`taskId`** maps to a `run_id` — represents a single execution of the agent

When you send a message, the response includes a `taskId` you can use to poll for results with `tasks/get`, or cancel with `tasks/cancel`.

## Authentication

A2A uses the same authentication as the rest of Aegra. If you have an `auth` handler configured in `aegra.json`, all A2A requests go through it.

Pass your token in the `Authorization` header:

```bash
curl -X POST http://localhost:2026/a2a/agent \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"messageId":"msg-1","role":"user","parts":[{"kind":"text","text":"Hello"}]}}}'
```

If no auth is configured, all A2A requests are allowed.

## Configuration

A2A is enabled by default. To disable it, set `disable_a2a` in the `http` section of `aegra.json`:

```json
{
  "graphs": {
    "agent": "./src/agent/graph.py:graph"
  },
  "http": {
    "disable_a2a": true
  }
}
```

See the [configuration reference](/reference/configuration) for all `http` options.
