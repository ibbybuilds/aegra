# Testing TypeScript Support

This guide explains how to test the TypeScript support implementation in Aegra.

## Prerequisites

1. **Install Node.js or Bun**:
   ```bash
   # Option 1: Install Bun (recommended - faster)
   curl -fsSL https://bun.sh/install | bash

   # Option 2: Install Node.js 20+
   nvm install 20
   nvm use 20
   ```

2. **Install Aegra dependencies**:
   ```bash
   cd aegra
   uv install
   source .venv/bin/activate
   ```

3. **Install TypeScript graph dependencies**:
   ```bash
   cd graphs/ts_example_agent
   bun install  # or: npm install
   cd ../..
   ```

## Unit Tests

Run the unit tests for configuration and detection:

```bash
# Run all tests
uv run pytest

# Run TypeScript-specific tests
uv run pytest tests/unit/test_core/test_config.py -v

# Run integration tests
uv run pytest tests/integration/test_typescript_graph.py -v
```

### Expected Output

```
tests/unit/test_core/test_config.py::TestIsNodeGraph::test_detects_typescript_extensions PASSED
tests/unit/test_core/test_config.py::TestIsNodeGraph::test_detects_javascript_extensions PASSED
tests/unit/test_core/test_config.py::TestValidateNodeVersion::test_validates_valid_versions PASSED
...
```

## Manual Testing

### 1. Start Aegra Server

```bash
# Make sure aegra.json includes the TypeScript graph
cat aegra.json
# Should show:
# {
#   "graphs": {
#     "agent": "./graphs/react_agent/graph.py:graph",
#     "ts_agent": "./graphs/ts_example_agent/graph.ts:graph"
#   },
#   "node_version": "20"
# }

# Start PostgreSQL
docker compose up postgres -d

# Run migrations
python3 scripts/migrate.py upgrade

# Start server
uv run uvicorn src.agent_server.main:app --reload
```

### 2. Check Server Logs

When the server starts, you should see:

```
📘 Detected TypeScript graph: ts_agent
```

This confirms the TypeScript graph was detected and registered.

### 3. Test with Python SDK

Create a test file `test_ts_graph.py`:

```python
import asyncio
from langgraph_sdk import get_client

async def main():
    # Connect to Aegra
    client = get_client(url="http://localhost:8000")

    # Create assistant for TypeScript graph
    assistant = await client.assistants.create(
        graph_id="ts_agent",
        if_exists="do_nothing",
    )
    print(f"✓ Created assistant: {assistant['assistant_id']}")

    # Create thread
    thread = await client.threads.create()
    print(f"✓ Created thread: {thread['thread_id']}")

    # Stream execution
    print("✓ Running TypeScript graph...")
    stream = client.runs.stream(
        thread_id=thread["thread_id"],
        assistant_id=assistant["assistant_id"],
        input={
            "messages": [
                {"role": "human", "content": "Hello from Python!"}
            ]
        },
        stream_mode=["values"],
    )

    async for chunk in stream:
        print(f"  Event: {chunk.event}")
        if chunk.event == "values":
            print(f"  Data: {chunk.data}")

    print("✓ TypeScript graph executed successfully!")

asyncio.run(main())
```

Run it:

```bash
uv run python test_ts_graph.py
```

### 4. Test with TypeScript SDK

Create a test file `test_ts_sdk.ts`:

```typescript
import { getClient } from "./sdk/src/index.js";

async function main() {
  // Connect to Aegra
  const client = getClient({ url: "http://localhost:8000" });

  // Create assistant
  const assistant = await client.assistants.create({
    graph_id: "ts_agent",
    if_exists: "do_nothing",
  });
  console.log(`✓ Created assistant: ${assistant.assistant_id}`);

  // Create thread
  const thread = await client.threads.create();
  console.log(`✓ Created thread: ${thread.thread_id}`);

  // Stream execution
  console.log("✓ Running TypeScript graph with TypeScript SDK...");
  const stream = client.runs.stream({
    thread_id: thread.thread_id,
    assistant_id: assistant.assistant_id,
    input: {
      messages: [
        { role: "human", content: "Hello from TypeScript SDK!" }
      ],
    },
    stream_mode: ["values"],
  });

  for await (const event of stream) {
    console.log(`  Event: ${event.event}`);
    if (event.event === "values") {
      console.log(`  Data:`, event.data);
    }
  }

  console.log("✓ TypeScript SDK works!");
}

main();
```

Run it:

```bash
# Build SDK first
cd sdk
bun run build
cd ..

# Run test
bun run test_ts_sdk.ts
```

## What to Verify

### ✅ Configuration Detection

- [ ] Server logs show "📘 Detected TypeScript graph: ts_agent"
- [ ] Both Python and TypeScript graphs are registered
- [ ] `node_version` is recognized in aegra.json

### ✅ Graph Execution

- [ ] TypeScript graph can be created as assistant
- [ ] Threads can be created
- [ ] Streaming works for TypeScript graphs
- [ ] Response contains expected data
- [ ] No errors in server logs

### ✅ SDK Functionality

- [ ] TypeScript SDK can connect to server
- [ ] All CRUD operations work (create, get, list, delete)
- [ ] Streaming returns proper events
- [ ] Types are correctly inferred in TypeScript

### ✅ Mixed Python/TypeScript

- [ ] Both graph types work in same server
- [ ] No conflicts between runtimes
- [ ] State persistence works for both

## Debugging

### Issue: "TypeScript graph wrapper not found"

**Solution**: The wrapper script file is missing. Check that `src/agent_server/core/ts_graph_wrapper.ts` exists.

### Issue: "No JavaScript runtime found"

**Solution**: Install Node.js 20+ or Bun:

```bash
curl -fsSL https://bun.sh/install | bash
```

### Issue: TypeScript graph dependencies not found

**Solution**: Install dependencies in the graph directory:

```bash
cd graphs/ts_example_agent
bun install
```

### Issue: Module import errors in wrapper

**Cause**: The TypeScript wrapper needs to import LangGraph modules.

**Solution**: Make sure the wrapper can find dependencies. You may need to install them globally or adjust the import paths.

### Issue: PostgreSQL connection errors

**Solution**: Ensure PostgreSQL is running and migrations are applied:

```bash
docker compose up postgres -d
python3 scripts/migrate.py upgrade
```

## CI/CD Testing

To run tests in CI/CD:

```yaml
# .github/workflows/test-typescript.yml
name: Test TypeScript Support

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Bun
        uses: oven-sh/setup-bun@v1
        with:
          bun-version: latest

      - name: Install Python dependencies
        run: |
          pip install uv
          uv install

      - name: Install TS graph dependencies
        run: |
          cd graphs/ts_example_agent
          bun install

      - name: Run tests
        run: uv run pytest tests/unit/test_core/test_config.py -v
```

## Performance Testing

Test TypeScript graph performance vs Python:

```python
import time
import asyncio
from langgraph_sdk import get_client

async def benchmark():
    client = get_client(url="http://localhost:8000")

    # Test Python graph
    start = time.time()
    py_assistant = await client.assistants.create(graph_id="agent")
    py_time = time.time() - start
    print(f"Python graph load time: {py_time:.3f}s")

    # Test TypeScript graph
    start = time.time()
    ts_assistant = await client.assistants.create(graph_id="ts_agent")
    ts_time = time.time() - start
    print(f"TypeScript graph load time: {ts_time:.3f}s")

    # Note: First TS load includes Node.js startup overhead

asyncio.run(benchmark())
```

## Next Steps

After successful testing:

1. Create more complex TypeScript graphs
2. Add tool calling examples
3. Test with real LLM integrations
4. Benchmark production workloads
5. Add e2e tests with actual LLM calls

## Reporting Issues

If you find issues, please include:

- Node.js/Bun version (`node --version` or `bun --version`)
- Python version (`python --version`)
- Error messages from server logs
- Steps to reproduce
- Expected vs actual behavior
