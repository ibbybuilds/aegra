# TypeScript Support in Aegra

Aegra now supports both Python and TypeScript/JavaScript LangGraph agents, making it a true drop-in replacement for LangGraph Platform with full language flexibility.

## Overview

TypeScript support enables two key capabilities:

1. **Server-Side**: Execute LangGraph agents written in TypeScript/JavaScript
2. **Client-Side**: Interact with Aegra using the TypeScript SDK

## Quick Start

### 1. Configure aegra.json

Add TypeScript graphs to your configuration:

```json
{
  "graphs": {
    "python_agent": "./graphs/react_agent/graph.py:graph",
    "ts_agent": "./graphs/ts_agent/graph.ts:graph"
  },
  "node_version": "20"
}
```

### 2. Create a TypeScript Graph

Create a LangGraph agent in TypeScript:

```typescript
// graphs/my_agent/graph.ts
import { StateGraph, Annotation } from "@langchain/langgraph";

const StateAnnotation = Annotation.Root({
  messages: Annotation<Array<{ role: string; content: string }>>({
    reducer: (left, right) => left.concat(right),
    default: () => [],
  }),
});

async function callModel(state, config) {
  const lastMessage = state.messages[state.messages.length - 1];
  return {
    messages: [{
      role: "assistant",
      content: `Response to: ${lastMessage.content}`,
    }],
  };
}

const workflow = new StateGraph(StateAnnotation)
  .addNode("callModel", callModel)
  .addEdge("__start__", "callModel")
  .addEdge("callModel", "__end__");

export const graph = workflow.compile();
graph.name = "My TypeScript Agent";
```

### 3. Install Dependencies

In your TypeScript graph directory:

```bash
cd graphs/my_agent
bun install @langchain/langgraph @langchain/langgraph-checkpoint-postgres
```

### 4. Use the TypeScript SDK

```typescript
import { getClient } from "@aegra/sdk";

const client = getClient({ url: "http://localhost:8000" });

// Create assistant
const assistant = await client.assistants.create({
  graph_id: "ts_agent",
  if_exists: "do_nothing",
});

// Create thread
const thread = await client.threads.create();

// Stream responses
const stream = client.runs.stream({
  thread_id: thread.thread_id,
  assistant_id: assistant.assistant_id,
  input: {
    messages: [{ role: "human", content: "Hello!" }],
  },
});

for await (const event of stream) {
  console.log(event);
}
```

## Architecture

### How It Works

1. **Detection**: Aegra detects TypeScript graphs by file extension (.ts, .js, .mts, etc.)
2. **Runtime**: TypeScript graphs execute in separate Node.js/Bun processes
3. **Communication**: JSON-based IPC for streaming results back to Python
4. **Persistence**: Same PostgreSQL checkpointer used for both Python and TypeScript graphs

```
┌─────────────────────────────────────────────┐
│           Aegra Server (Python)             │
│  ┌──────────────┐       ┌────────────────┐ │
│  │ FastAPI Layer│       │ Graph Loader   │ │
│  └──────┬───────┘       └────────┬───────┘ │
│         │                        │         │
│         │    ┌───────────────────┼────┐    │
│         │    │                   │    │    │
│         v    v                   v    v    │
│    Python Graphs          TypeScript       │
│    (Direct Import)        Runtime Mgr      │
│         │                      │           │
│         │                      v           │
│         │              Node.js Process     │
│         │              ┌──────────────┐    │
│         │              │ TS Graph     │    │
│         │              │ Wrapper      │    │
│         │              └──────────────┘    │
│         │                      │           │
│         v                      v           │
│    ┌────────────────────────────────────┐  │
│    │   PostgreSQL Checkpointer          │  │
│    │   (Shared State Persistence)       │  │
│    └────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Configuration Reference

### aegra.json Schema

```typescript
{
  // Graph definitions (required)
  "graphs": {
    "graph_name": "./path/to/file.py:export_name",  // Python
    "ts_graph": "./path/to/file.ts:export_name"     // TypeScript
  },

  // Node.js version for TypeScript graphs (optional, auto-detected)
  "node_version": "20",  // Minimum: 20

  // Other Aegra configuration...
  "dependencies": [...],
  "env": {...}
}
```

## TypeScript Graph Guidelines

### Project Structure

```
graphs/my_ts_agent/
├── graph.ts          # Main graph definition
├── package.json      # Dependencies
├── tsconfig.json     # TypeScript configuration
└── README.md         # Documentation
```

### Required Dependencies

```json
{
  "dependencies": {
    "@langchain/langgraph": "^0.2.0",
    "@langchain/langgraph-checkpoint-postgres": "^0.0.13",
    "@langchain/core": "^0.3.0"
  }
}
```

### Best Practices

1. **Export the graph**: Always export a compiled graph as `graph`
2. **Use TypeScript**: Leverage type safety for better reliability
3. **State management**: Use `Annotation` for type-safe state
4. **Checkpointing**: Let Aegra handle checkpointer injection
5. **Error handling**: Implement proper error handling in nodes

### Example with LLM Integration

```typescript
import { StateGraph, Annotation } from "@langchain/langgraph";
import { ChatAnthropic } from "@langchain/anthropic";

const StateAnnotation = Annotation.Root({
  messages: Annotation<Array<any>>({
    reducer: (left, right) => left.concat(right),
    default: () => [],
  }),
});

async function callModel(state, config) {
  const model = new ChatAnthropic({
    model: "claude-3-5-sonnet-20240620",
    apiKey: process.env.ANTHROPIC_API_KEY,
  });

  const response = await model.invoke(state.messages);

  return {
    messages: [response],
  };
}

const workflow = new StateGraph(StateAnnotation)
  .addNode("agent", callModel)
  .addEdge("__start__", "agent")
  .addEdge("agent", "__end__");

export const graph = workflow.compile();
```

## TypeScript SDK Reference

### Installation

```bash
bun add @aegra/sdk
```

### Basic Usage

```typescript
import { getClient } from "@aegra/sdk";

const client = getClient({
  url: "http://localhost:8000",
  apiKey: "optional-api-key",
  timeout: 30000,  // 30 seconds
});
```

### API Methods

#### Assistants

```typescript
// Create assistant
const assistant = await client.assistants.create({
  graph_id: "my_agent",
  name: "My Assistant",
  config: { temperature: 0.7 },
  if_exists: "do_nothing", // or "update" or "error"
});

// Get assistant
const assistant = await client.assistants.get(assistant_id);

// List assistants
const assistants = await client.assistants.list();

// Delete assistant
await client.assistants.delete(assistant_id);
```

#### Threads

```typescript
// Create thread
const thread = await client.threads.create({
  metadata: { user_id: "user123" },
});

// Get thread
const thread = await client.threads.get(thread_id);

// Delete thread
await client.threads.delete(thread_id);
```

#### Runs

```typescript
// Stream run
const stream = client.runs.stream({
  thread_id: thread.thread_id,
  assistant_id: assistant.assistant_id,
  input: {
    messages: [
      { role: "human", content: "Hello!" }
    ],
  },
  stream_mode: ["values", "messages-tuple"],
  on_disconnect: "cancel",  // or "continue"
});

for await (const event of stream) {
  if (event.event === "values") {
    console.log("State update:", event.data);
  } else if (event.event === "messages-tuple") {
    console.log("Message:", event.data);
  }
}
```

## Runtime Requirements

### Node.js / Bun

- **Minimum Node.js version**: 20
- **Recommended**: Latest Bun (faster startup, better TypeScript support)

Aegra automatically detects and uses Bun if available, otherwise falls back to Node.js.

### Installation

```bash
# Install bun (recommended)
curl -fsSL https://bun.sh/install | bash

# Or use Node.js 20+
nvm install 20
nvm use 20
```

## State Persistence

TypeScript graphs use the **same PostgreSQL database** as Python graphs for state persistence.

### Automatic Checkpointing

Aegra automatically provides a PostgreSQL checkpointer to TypeScript graphs:

```typescript
// No need to manually create checkpointer
export const graph = workflow.compile();
// Aegra injects checkpointer automatically
```

### Shared State

State is fully compatible between Python and TypeScript graphs:

- Same thread can be used across both
- Checkpoint format is identical
- State history is preserved

## Troubleshooting

### Graph Not Loading

**Error**: `TypeScript graph wrapper not found`

**Solution**: Ensure the `ts_graph_wrapper.ts` file exists in `src/agent_server/core/`

### Node.js Not Found

**Error**: `No JavaScript runtime found`

**Solution**: Install Node.js 20+ or Bun

```bash
# Install bun
curl -fsSL https://bun.sh/install | bash

# Or install Node.js
nvm install 20
```

### Module Import Errors

**Error**: `Cannot find module '@langchain/langgraph'`

**Solution**: Install dependencies in your graph directory

```bash
cd graphs/my_ts_agent
bun install
```

### Type Errors

**Error**: TypeScript compilation errors

**Solution**: Ensure you have proper type definitions

```bash
bun add -D @types/node typescript
```

## Mixing Python and TypeScript

You can run both Python and TypeScript graphs in the same Aegra instance:

```json
{
  "graphs": {
    "python_agent": "./graphs/py_agent/graph.py:graph",
    "ts_agent": "./graphs/ts_agent/graph.ts:graph",
    "another_py": "./graphs/another/graph.py:graph"
  },
  "node_version": "20"
}
```

Both types of graphs:
- Share the same PostgreSQL database
- Use the same API endpoints
- Support the same features (streaming, checkpointing, etc.)
- Are accessed via the same SDK

## Performance Considerations

### Startup Time

- **Python graphs**: ~100-500ms (direct import)
- **TypeScript graphs**: ~1-3s (Node.js process spawn + module load)

### Runtime Performance

- Both Python and TypeScript graphs have similar runtime performance
- Bun provides faster startup than Node.js
- Consider process pooling for high-throughput scenarios

### Resource Usage

- Each TypeScript graph runs in a separate process
- Memory overhead: ~50-100MB per active TypeScript graph
- Python graphs share the main process

## Examples

See the `graphs/ts_example_agent/` directory for a complete example.

## Migration from LangGraph Platform

Aegra with TypeScript support is designed as a drop-in replacement:

1. **Same SDK**: Use `@aegra/sdk` just like `@langchain/langgraph-sdk`
2. **Same graph format**: Existing TypeScript graphs work without changes
3. **Same API**: All endpoints are compatible

Simply point your existing LangGraph TypeScript graphs and SDK usage to your Aegra instance.

## Next Steps

- Explore the [TypeScript SDK Reference](../sdk/README.md)
- Check out [Example TypeScript Graph](../graphs/ts_example_agent/)
- Read the [Aegra Developer Guide](./developer-guide.md)
