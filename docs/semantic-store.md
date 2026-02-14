# Semantic Store Configuration

Aegra supports semantic similarity search through the LangGraph Store API using PostgreSQL with pgvector. This enables agents to store and retrieve information based on meaning rather than exact keyword matches.

## Overview

When configured, Aegra automatically embeds stored items using your chosen embedding model and enables semantic search queries. This is useful for:

- **Conversational Memory**: Agents can recall past interactions semantically
- **RAG Applications**: Store and retrieve knowledge documents based on similarity
- **Personalization**: Remember user preferences and retrieve them contextually
- **Multi-tenant Applications**: Namespaced semantic search per user/tenant

## Configuration

Add the `store` section to your `aegra.json`:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "store": {
    "index": {
      "dims": 1536,
      "embed": "openai:text-embedding-3-small",
      "fields": ["$"]
    }
  }
}
```

### Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `dims` | `integer` | Yes | Embedding vector dimensions (must match your model) |
| `embed` | `string` | Yes | Embedding model in format `<provider>:<model-id>` |
| `fields` | `list[str]` | No | JSON fields to embed (default: `["$"]` for entire document) |

### Fields Configuration

The `fields` option controls which parts of your documents are embedded:

| Value | Behavior |
|-------|----------|
| `["$"]` (default) | Embed the entire document as one unit |
| `["text", "summary"]` | Embed only these top-level fields |
| `["metadata.title", "content.text"]` | Use JSON path notation for nested fields |

**Example with specific fields:**
```json
{
  "store": {
    "index": {
      "dims": 1536,
      "embed": "openai:text-embedding-3-small",
      "fields": ["text", "summary"]
    }
  }
}
```

Documents missing specified fields will still be stored but won't have embeddings for those fields. You can also override which fields to embed at put time using the `index` parameter.

### Supported Embedding Providers

| Provider | Model | Dimensions | Example |
|----------|-------|------------|---------|
| OpenAI | text-embedding-3-small | 1536 | `openai:text-embedding-3-small` |
| OpenAI | text-embedding-3-large | 3072 | `openai:text-embedding-3-large` |
| AWS Bedrock | amazon.titan-embed-text-v2:0 | 1024 | `bedrock:amazon.titan-embed-text-v2:0` |
| Cohere | embed-english-v3.0 | 1024 | `cohere:embed-english-v3.0` |

## Environment Variables

Ensure the appropriate API key is set for your embedding provider:

```bash
# For OpenAI embeddings
OPENAI_API_KEY=sk-...

# For AWS Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# For Cohere
COHERE_API_KEY=...
```

## Database Requirements

Semantic store requires PostgreSQL with the pgvector extension. The recommended Docker image is:

```yaml
postgres:
  image: pgvector/pgvector:pg18
```

Aegra automatically creates the necessary tables and indexes during startup via `AsyncPostgresStore.setup()`.

## Usage Example

### Storing Items

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8000")

# Store user preferences
await client.store.put(
    namespace=["user", "123", "preferences"],
    key="coding_style",
    value={
        "text": "I prefer clean code with descriptive variable names and minimal comments"
    }
)
```

### Semantic Search

```python
# Search finds items by meaning, not exact keywords
results = await client.store.search(
    namespace_prefix=["user", "123"],
    query="How does this user like to write code?",
    limit=5
)
# Returns the coding_style preference based on semantic similarity
```

## Verification

After starting Aegra with semantic store configured, you should see this log message:

```
INFO: Semantic store enabled with embeddings: openai:text-embedding-3-small
```

## Backward Compatibility

If no `store.index` configuration is provided, Aegra operates in basic key-value mode (default behavior). This ensures backward compatibility with existing deployments.

## Troubleshooting

### "pgvector extension not found"
Ensure you're using a PostgreSQL image with pgvector installed (`pgvector/pgvector:pg18`).

### "Invalid embedding model"
Verify the `embed` format is correct (`provider:model-id`) and the corresponding API key is set.

### "Dimension mismatch"
Ensure `dims` matches your embedding model's output dimensions exactly.
