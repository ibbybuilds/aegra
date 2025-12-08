# TypeScript Example Agent

This is a simple TypeScript LangGraph agent that demonstrates integration with Aegra.

## Structure

- **graph.ts**: Main graph definition with state and nodes
- **package.json**: Dependencies including @langchain/langgraph
- **tsconfig.json**: TypeScript configuration

## How it Works

1. The agent maintains a conversation state with message history
2. When a user sends a message, it's processed by the `callModel` node
3. The agent responds with a simple acknowledgment (can be extended with real LLM calls)
4. State is persisted to PostgreSQL via the checkpoint system

## Running

This graph is automatically loaded by Aegra when configured in aegra.json:

```json
{
  "graphs": {
    "ts_agent": "./graphs/ts_example_agent/graph.ts:graph"
  },
  "node_version": "20"
}
```

## Dependencies

Install dependencies with bun:

```bash
bun install
```

## Future Enhancements

- Add real LLM integration (Anthropic, OpenAI, etc.)
- Implement tool calling
- Add more complex conversation logic
- Support streaming responses
