# SSE Streaming API Documentation

This document provides comprehensive documentation for Aegra's Server-Sent Events (SSE) streaming API, including exact wire format examples and client consumption patterns.

## Table of Contents

- [Overview](#overview)
- [SSE Wire Format](#sse-wire-format)
- [HTTP Headers](#http-headers)
- [Event Types](#event-types)
- [Event ID Format](#event-id-format)
- [Subgraph Events](#subgraph-events)
- [Client Examples](#client-examples)
- [Error Handling](#error-handling)
- [LangSmith Studio Compatibility](#langsmith-studio-compatibility)

---

## Overview

Aegra uses Server-Sent Events (SSE) to stream real-time updates from LangGraph execution to clients. SSE provides a unidirectional event stream over HTTP, making it ideal for streaming LLM responses, state updates, and debug information.

**Key Features:**
- Real-time token streaming from LLMs
- State updates as the graph executes
- Debug information for development
- Automatic reconnection support via event IDs
- Multi-tenant support with user context

**API Endpoint:**
```
POST /threads/{thread_id}/runs/stream
```

---

## SSE Wire Format

SSE events follow the [W3C Server-Sent Events specification](https://html.spec.whatwg.org/multipage/server-sent-events.html). Each event consists of:

```
event: <event_type>
data: <json_payload>
id: <event_id>

```

**Important:** Each event MUST end with two newlines (`\n\n`). The blank line signals the end of the event.

### Basic Example

**Wire format:**
```
event: values
data: {"messages":[{"role":"user","content":"hello"}]}
id: run-123_event_1

```

**Parsed by client:**
```javascript
{
  event: "values",
  data: {"messages":[{"role":"user","content":"hello"}]},
  id: "run-123_event_1"
}
```

---

## HTTP Headers

All SSE responses include these headers:

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Last-Event-ID
```

**Header Explanation:**
- `Content-Type: text/event-stream` - Identifies the response as SSE
- `Cache-Control: no-cache` - Prevents caching of the stream
- `Connection: keep-alive` - Maintains the connection for streaming
- `Access-Control-Allow-Origin: *` - Allows cross-origin requests
- `Access-Control-Allow-Headers: Last-Event-ID` - Supports reconnection

---

## Event Types

### 1. metadata

**Purpose:** Sent at the start of a run to provide run identification and attempt information.

**Wire format:**
```
event: metadata
data: {"run_id":"run-abc123","attempt":1}
id: run-abc123_event_0

```

**Data structure:**
```typescript
{
  run_id: string,     // Unique run identifier
  attempt: number     // Attempt number (for retries)
}
```

**When sent:** First event in every stream

---

### 2. messages

**Purpose:** Streams LLM token chunks in real-time (token-by-token streaming).

**Wire format (tuple format):**
```
event: messages
data: [{"id":"msg-xyz","type":"ai","content":"Hello"},{"model":"gpt-4","usage":{"input_tokens":10,"output_tokens":5}}]
id: run-abc123_event_1

```

**Data structure (tuple format):**
```typescript
[
  {
    // Message chunk (first element)
    id?: string,
    type: "ai" | "human" | "system",
    content: string,
    tool_calls?: Array<ToolCall>
  },
  {
    // Metadata (second element)
    model?: string,
    usage?: {
      input_tokens: number,
      output_tokens: number
    },
    finish_reason?: string
  }
]
```

**Wire format (list format):**
```
event: messages
data: [{"role":"user","content":"hello"}]
id: run-abc123_event_1

```

**When sent:** When using `stream_mode=["messages"]` or `stream_mode=["messages-tuple"]`

**Related event types:**
- `messages/partial` - Partial message updates (Studio)
- `messages/complete` - Completed messages (Studio)
- `messages/metadata` - Message metadata (Studio)

---

### 3. values

**Purpose:** Sends complete state snapshots after each node execution.

**Wire format:**
```
event: values
data: {"messages":[{"role":"user","content":"hello"},{"role":"assistant","content":"Hi there!"}],"context":{"user_id":"user-123"}}
id: run-abc123_event_5

```

**Data structure:**
```typescript
// Entire graph state (structure depends on your StateGraph definition)
{
  [key: string]: any
}
```

**When sent:**
- After each node completes (when using `stream_mode=["values"]`)
- Contains the FULL state after the node update

**Example sequence:**
```
event: values
data: {"messages":[{"role":"user","content":"hello"}],"step":1}
id: run-abc123_event_1

event: values
data: {"messages":[{"role":"user","content":"hello"},{"role":"assistant","content":"Hi!"}],"step":2}
id: run-abc123_event_2

```

---

### 4. updates

**Purpose:** Sends incremental state changes (deltas) from each node.

**Wire format:**
```
event: updates
data: {"agent":{"messages":[{"role":"assistant","content":"Processing..."}]}}
id: run-abc123_event_3

```

**Data structure:**
```typescript
{
  [node_name: string]: {
    // Partial state update from this node
    [key: string]: any
  }
}
```

**When sent:** When using `stream_mode=["updates"]`

**Special case - Interrupts:**
When an interrupt occurs, updates events are converted to values events:
```
event: values
data: {"__interrupt__":[{"value":"confirm","resumable":true}]}
id: run-abc123_event_4

```

---

### 5. debug

**Purpose:** Provides detailed execution information for debugging and LangSmith Studio integration.

**Wire format:**
```
event: debug
data: {"type":"task_result","timestamp":"2026-01-27T10:00:00Z","payload":{"type":"task","name":"agent","input":{"messages":[{"role":"user","content":"hello"}]},"checkpoint":{"thread_id":"thread-123","checkpoint_id":"1ef89-abc","checkpoint_ns":""},"parent_checkpoint":{"thread_id":"thread-123","checkpoint_id":"1ef88-xyz","checkpoint_ns":""}}}
id: run-abc123_event_2

```

**Data structure:**
```typescript
{
  type: string,              // Event type (e.g., "task_result", "checkpoint")
  timestamp?: string,         // ISO 8601 timestamp
  payload: {
    type?: string,            // Task type
    name?: string,            // Node/task name
    input?: any,              // Input data
    checkpoint?: {
      thread_id: string,
      checkpoint_id: string,
      checkpoint_ns: string
    },
    parent_checkpoint?: {
      thread_id: string,
      checkpoint_id: string,
      checkpoint_ns: string
    } | null,
    [key: string]: any
  }
}
```

**When sent:** When using `stream_mode=["debug"]`

**Note:** Checkpoint fields are automatically extracted from `config.configurable` for LangSmith Studio compatibility.

---

### 6. end

**Purpose:** Signals successful completion of the stream.

**Wire format:**
```
event: end
data: {"status":"success"}
id: run-abc123_event_10

```

**Data structure:**
```typescript
{
  status: "success"
}
```

**When sent:** After all graph execution completes successfully

**Note:** Always the final event in a successful stream.

---

### 7. error

**Purpose:** Reports errors during execution.

**Wire format:**
```
event: error
data: {"error":"Tool 'search_tool' not found","timestamp":"2026-01-27T10:00:00Z"}
id: run-abc123_event_5

```

**Data structure:**
```typescript
{
  error: string,       // Error message
  timestamp: string    // ISO 8601 timestamp
}
```

**When sent:** When an error occurs during graph execution

---

### 8. state

**Purpose:** Advanced state information (rarely used directly).

**Wire format:**
```
event: state
data: {"values":{"messages":[...]},"next":["agent"],"config":{"configurable":{"thread_id":"thread-123"}}}
id: run-abc123_event_6

```

---

### 9. logs

**Purpose:** Streaming logs from the graph execution.

**Wire format:**
```
event: logs
data: {"level":"info","message":"Starting agent node","timestamp":"2026-01-27T10:00:00Z"}
id: run-abc123_event_7

```

---

### 10. tasks

**Purpose:** Pending or background tasks information.

**Wire format:**
```
event: tasks
data: [{"id":"task-1","name":"agent","path":["agent"],"error":null}]
id: run-abc123_event_8

```

---

## Event ID Format

Event IDs follow the format: `{run_id}_event_{sequence}`

**Examples:**
```
run-abc123_event_0
run-abc123_event_1
run-abc123_event_2
```

**Purpose:**
- Enables clients to resume from last received event
- Monotonically increasing sequence ensures ordering
- Client sends `Last-Event-ID` header on reconnection

**Reconnection example:**
```http
GET /threads/thread-123/runs/stream
Last-Event-ID: run-abc123_event_5
```

Server resumes from event 6.

---

## Subgraph Events

When using `subgraphs=True` in streaming configuration, events from nested subgraphs are namespaced.

### Format

Event types are prefixed with namespace using pipe (`|`) separator:

```
event: <event_type>|<namespace1>|<namespace2>|...
```

### Example

**Parent graph event:**
```
event: messages
data: [{"type":"ai","content":"I'll search for that"}]
id: run-abc123_event_1

```

**Subgraph event:**
```
event: messages|search_agent
data: [{"type":"ai","content":"Searching..."}]
id: run-abc123_event_2

```

**Nested subgraph event:**
```
event: values|research_agent|web_scraper
data: {"url":"https://example.com","status":"fetching"}
id: run-abc123_event_3

```

### Namespace Extraction

The namespace is extracted from LangGraph's 3-tuple format:
```python
(namespace, mode, chunk)
```

Where:
- `namespace`: List/tuple of subgraph names (e.g., `["search_agent"]`)
- `mode`: Event type (e.g., `"messages"`, `"values"`)
- `chunk`: Event payload

---

## Client Examples

### JavaScript (Browser)

```javascript
const eventSource = new EventSource(
  'http://localhost:8000/threads/thread-123/runs/stream',
  {
    withCredentials: true,
    headers: {
      'Authorization': 'Bearer <token>'
    }
  }
);

// Listen to specific event types
eventSource.addEventListener('metadata', (event) => {
  const data = JSON.parse(event.data);
  console.log('Run ID:', data.run_id);
});

eventSource.addEventListener('messages', (event) => {
  const data = JSON.parse(event.data);
  const [messageChunk, metadata] = data;

  // Append token to UI
  appendToken(messageChunk.content);
});

eventSource.addEventListener('values', (event) => {
  const state = JSON.parse(event.data);
  console.log('State update:', state);
});

eventSource.addEventListener('end', (event) => {
  const data = JSON.parse(event.data);
  console.log('Stream completed:', data.status);
  eventSource.close();
});

eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  console.error('Error:', data.error);
  eventSource.close();
});

// Handle connection errors
eventSource.onerror = (error) => {
  console.error('Connection error:', error);
  eventSource.close();
};
```

### JavaScript (Node.js with eventsource)

```javascript
import EventSource from 'eventsource';

const eventSource = new EventSource(
  'http://localhost:8000/threads/thread-123/runs/stream',
  {
    headers: {
      'Authorization': 'Bearer <token>'
    }
  }
);

eventSource.addEventListener('messages', (event) => {
  const data = JSON.parse(event.data);
  const [messageChunk, metadata] = data;

  process.stdout.write(messageChunk.content);
});

eventSource.addEventListener('end', () => {
  console.log('\n\nStream completed');
  eventSource.close();
});
```

### Python (httpx)

```python
import json
import httpx

url = "http://localhost:8000/threads/thread-123/runs/stream"
headers = {"Authorization": "Bearer <token>"}

with httpx.stream("POST", url, headers=headers, timeout=None) as response:
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_type = line.split("event: ")[1]
        elif line.startswith("data: "):
            data = json.loads(line.split("data: ")[1])

            if event_type == "messages":
                message_chunk, metadata = data
                print(message_chunk["content"], end="", flush=True)
            elif event_type == "end":
                print("\n\nStream completed")
                break
            elif event_type == "error":
                print(f"\n\nError: {data['error']}")
                break
```

### Python (LangGraph SDK Client)

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")

# Token streaming with messages-tuple mode
async for chunk in client.runs.stream(
    thread_id="thread-123",
    assistant_id="asst-123",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    stream_mode=["messages-tuple", "values"]
):
    if chunk.event == "messages":
        message_chunk, metadata = chunk.data
        print(message_chunk["content"], end="", flush=True)
    elif chunk.event == "values":
        print(f"\nState: {chunk.data}")
    elif chunk.event == "end":
        print("\nCompleted!")
```

### Handling Reconnection

```javascript
function createReconnectingEventSource(url) {
  let lastEventId = null;
  let eventSource = null;

  function connect() {
    const reconnectUrl = lastEventId
      ? `${url}?lastEventId=${lastEventId}`
      : url;

    eventSource = new EventSource(reconnectUrl);

    eventSource.addEventListener('message', (event) => {
      lastEventId = event.lastEventId;
      // Process event...
    });

    eventSource.onerror = () => {
      eventSource.close();
      setTimeout(connect, 3000); // Reconnect after 3s
    };
  }

  connect();
  return eventSource;
}
```

---

## Error Handling

### Client-Side Error Handling

**Connection Errors:**
```javascript
eventSource.onerror = (error) => {
  if (eventSource.readyState === EventSource.CLOSED) {
    console.log('Connection closed');
  } else if (eventSource.readyState === EventSource.CONNECTING) {
    console.log('Reconnecting...');
  }
};
```

**Server-Side Errors (error event):**
```javascript
eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  displayErrorMessage(data.error);
  eventSource.close();
});
```

### Common Error Scenarios

1. **Authentication failure:**
   - HTTP 401 response
   - Connection immediately closes
   - Client should refresh token and reconnect

2. **Graph execution error:**
   - Receives `error` event
   - Contains error message and timestamp
   - Stream ends after error event

3. **Network interruption:**
   - `onerror` fires with `readyState === CONNECTING`
   - Browser automatically attempts reconnection
   - Server resumes from `Last-Event-ID` if sent

4. **Timeout:**
   - Server closes connection after inactivity
   - Client receives close event
   - Should reconnect with last event ID

---

## LangSmith Studio Compatibility

Aegra's SSE implementation is compatible with LangSmith Studio's streaming protocol.

### Checkpoint Fields

Debug events automatically include checkpoint information:

```json
{
  "type": "task_result",
  "payload": {
    "checkpoint": {
      "thread_id": "thread-123",
      "checkpoint_id": "1ef89-abc",
      "checkpoint_ns": ""
    },
    "parent_checkpoint": {
      "thread_id": "thread-123",
      "checkpoint_id": "1ef88-xyz",
      "checkpoint_ns": ""
    }
  }
}
```

These fields are extracted from:
- `config.configurable` → `checkpoint`
- `parent_config.configurable` → `parent_checkpoint`

### Studio-Specific Event Types

- `messages/partial` - Partial message updates
- `messages/complete` - Completed messages
- `messages/metadata` - Message metadata

These events pass through as-is for Studio compatibility.

### End Event Format

Studio expects `status: "success"` (not `"completed"`):

```json
{"status": "success"}
```

---

## Complete Example Stream

Here's a complete example of an SSE stream from start to finish:

```
event: metadata
data: {"run_id":"run-abc123","attempt":1}
id: run-abc123_event_0

event: values
data: {"messages":[{"role":"user","content":"What's the weather?"}],"step":0}
id: run-abc123_event_1

event: messages
data: [{"type":"ai","content":"Let"},{"model":"gpt-4"}]
id: run-abc123_event_2

event: messages
data: [{"type":"ai","content":" me"},{"model":"gpt-4"}]
id: run-abc123_event_3

event: messages
data: [{"type":"ai","content":" check"},{"model":"gpt-4"}]
id: run-abc123_event_4

event: messages
data: [{"type":"ai","content":" that"},{"model":"gpt-4"}]
id: run-abc123_event_5

event: values
data: {"messages":[{"role":"user","content":"What's the weather?"},{"role":"assistant","content":"Let me check that","tool_calls":[{"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\"location\":\"San Francisco\"}"}}]}],"step":1}
id: run-abc123_event_6

event: values
data: {"messages":[{"role":"user","content":"What's the weather?"},{"role":"assistant","content":"Let me check that","tool_calls":[{"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\"location\":\"San Francisco\"}"}}]},{"role":"tool","tool_call_id":"call-1","content":"72°F, sunny"}],"step":2}
id: run-abc123_event_7

event: messages
data: [{"type":"ai","content":"It's"},{"model":"gpt-4"}]
id: run-abc123_event_8

event: messages
data: [{"type":"ai","content":" 72"},{"model":"gpt-4"}]
id: run-abc123_event_9

event: messages
data: [{"type":"ai","content":"°F"},{"model":"gpt-4"}]
id: run-abc123_event_10

event: messages
data: [{"type":"ai","content":" and"},{"model":"gpt-4"}]
id: run-abc123_event_11

event: messages
data: [{"type":"ai","content":" sunny"},{"model":"gpt-4"}]
id: run-abc123_event_12

event: values
data: {"messages":[{"role":"user","content":"What's the weather?"},{"role":"assistant","content":"Let me check that","tool_calls":[{"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\"location\":\"San Francisco\"}"}}]},{"role":"tool","tool_call_id":"call-1","content":"72°F, sunny"},{"role":"assistant","content":"It's 72°F and sunny"}],"step":3}
id: run-abc123_event_13

event: end
data: {"status":"success"}
id: run-abc123_event_14

```

---

## Implementation Files

**Core Implementation:**
- `src/agent_server/core/sse.py` - SSE formatting functions
- `src/agent_server/services/event_converter.py` - Event conversion logic
- `src/agent_server/services/streaming_service.py` - Streaming orchestration
- `src/agent_server/utils/sse_utils.py` - Event ID utilities

**Tests:**
- `tests/unit/test_core/test_sse.py` - SSE formatting tests
- `tests/unit/test_services/test_event_converter.py` - Event conversion tests
- `tests/e2e/test_streaming/test_chat_streaming.py` - End-to-end streaming tests

---

## References

- [W3C Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [LangGraph Streaming Documentation](https://langchain-ai.github.io/langgraph/how-tos/streaming/)
- [Agent Protocol Specification](https://github.com/AI-Engineer-Foundation/agent-protocol)
