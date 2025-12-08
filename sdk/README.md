# @aegra/sdk

TypeScript/JavaScript SDK for [Aegra](https://github.com/ibbybuilds/aegra) - Self-hosted LangGraph Platform Alternative.

## Installation

```bash
# Using bun (recommended)
bun add @aegra/sdk

# Using npm
npm install @aegra/sdk

# Using yarn
yarn add @aegra/sdk
```

## Quick Start

```typescript
import { getClient } from "@aegra/sdk";

// Create client
const client = getClient({
  url: "http://localhost:8000",
  apiKey: "your-api-key", // Optional
});

// Create an assistant
const assistant = await client.assistants.create({
  graph_id: "agent",
  if_exists: "do_nothing",
});

// Create a thread
const thread = await client.threads.create();

// Stream responses
const stream = client.runs.stream({
  thread_id: thread.thread_id,
  assistant_id: assistant.assistant_id,
  input: {
    messages: [
      {
        role: "human",
        content: "Hello!",
      },
    ],
  },
  stream_mode: ["values", "messages-tuple"],
});

for await (const event of stream) {
  console.log(`Event: ${event.event}`, event.data);
}
```

## API Reference

### Client

#### `getClient(config: ClientConfig): AegraClient`

Create a new Aegra client.

**Config Options:**

- `url`: Base URL of your Aegra server (required)
- `apiKey`: API key for authentication (optional)
- `headers`: Additional headers to include in requests (optional)
- `timeout`: Request timeout in milliseconds (default: 30000)

### Assistants API

#### `client.assistants.create(options: CreateAssistantOptions): Promise<Assistant>`

Create a new assistant.

**Options:**

- `graph_id`: ID of the graph to use (required)
- `name`: Assistant name (optional)
- `description`: Assistant description (optional)
- `config`: Additional configuration (optional)
- `if_exists`: How to handle existing assistant ("do_nothing" | "update" | "error")

#### `client.assistants.get(assistantId: string): Promise<Assistant>`

Get an assistant by ID.

#### `client.assistants.list(): Promise<Assistant[]>`

List all assistants.

#### `client.assistants.delete(assistantId: string): Promise<void>`

Delete an assistant.

### Threads API

#### `client.threads.create(options?: CreateThreadOptions): Promise<Thread>`

Create a new conversation thread.

**Options:**

- `metadata`: Thread metadata (optional)

#### `client.threads.get(threadId: string): Promise<Thread>`

Get a thread by ID.

#### `client.threads.delete(threadId: string): Promise<void>`

Delete a thread.

### Runs API

#### `client.runs.stream(options: StreamRunOptions): AsyncIterable<StreamEvent>`

Stream run execution events.

**Options:**

- `thread_id`: Thread ID (required)
- `assistant_id`: Assistant ID (required)
- `input`: Input messages (required)
  - `messages`: Array of message objects
- `config`: Additional configuration (optional)
- `stream_mode`: Event types to stream (optional, default: ["values"])
- `on_disconnect`: Disconnect behavior ("cancel" | "continue", default: "cancel")

## TypeScript Support

The SDK is written in TypeScript and includes full type definitions.

```typescript
import type { Assistant, Thread, Message, StreamEvent } from "@aegra/sdk";
```

## Compatibility

This SDK is designed to be compatible with the LangGraph SDK API, making it easy to switch between LangGraph Platform and Aegra.

## License

Apache 2.0 - see [LICENSE](../LICENSE) file for details.
