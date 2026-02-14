# Configuration

Aegra uses JSON configuration files (`aegra.json` or `langgraph.json`) to configure graphs, authentication, HTTP settings, and more.

## Configuration File Resolution

Aegra resolves configuration files in this order:

1. **`AEGRA_CONFIG` environment variable** (if set) - absolute or relative path
2. **`aegra.json`** in current working directory
3. **`langgraph.json`** in current working directory (fallback for compatibility)

Example:

```bash
# Use custom config file
AEGRA_CONFIG=production.json aegra dev
# Or with uvicorn directly:
AEGRA_CONFIG=production.json uv run --package aegra-api uvicorn aegra_api.main:app

# Use default aegra.json
aegra dev
```

## Configuration Schema

### Complete Example

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph",
    "agent_hitl": "./graphs/react_agent_hitl/graph.py:graph"
  },
  "auth": {
    "path": "./jwt_mock_auth_example.py:auth",
    "disable_studio_auth": false
  },
  "http": {
    "app": "./custom_routes_example.py:app",
    "enable_custom_route_auth": false,
    "cors": {
      "allow_origins": ["https://example.com"],
      "allow_credentials": true
    }
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

## Graphs Configuration

Configure your LangGraph graphs:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph",
    "custom_agent": "./my_graphs/custom.py:my_graph"
  }
}
```

- **Key**: Graph ID (used in API calls)
- **Value**: Import path in format `'./path/to/file.py:variable'`

## Authentication Configuration

Configure authentication and authorization:

```json
{
  "auth": {
    "path": "./my_auth.py:auth",
    "disable_studio_auth": false
  }
}
```

### Options

- **`path`** (required): Import path to your auth handler
  - Format: `'./file.py:variable'` or `'module:variable'`
  - Examples:
    - `'./auth.py:auth'` - Load `auth` from `auth.py` in project root
    - `'./src/auth/jwt.py:auth'` - Load from nested path
    - `'mypackage.auth:auth'` - Load from installed package

- **`disable_studio_auth`** (optional, default: `false`): Disable authentication for LangGraph Studio connections

See [Authentication & Authorization](authentication.md) for complete documentation.

## HTTP Configuration

Configure custom routes and CORS:

```json
{
  "http": {
    "app": "./custom_routes_example.py:app",
    "enable_custom_route_auth": false,
    "cors": {
      "allow_origins": ["https://example.com"],
      "allow_credentials": true
    }
  }
}
```

### Options

- **`app`** (optional): Import path to custom FastAPI app
  - Format: `'./file.py:variable'`
  - Example: `'./custom_routes_example.py:app'`

- **`enable_custom_route_auth`** (optional, default: `false`): Require authentication for all custom routes by default

- **`cors`** (optional): CORS configuration
  - **`allow_origins`**: List of allowed origins (default: `["*"]`)
  - **`allow_credentials`**: Allow credentials in CORS requests (default: `true`)

See [Custom Routes](custom-routes.md) for more details.

## Store Configuration

Configure semantic store (vector embeddings):

```json
{
  "store": {
    "index": {
      "dims": 1536,
      "embed": "openai:text-embedding-3-small",
      "fields": ["$"]
    }
  }
}
```

### Options

- **`index`** (optional): Vector index configuration
  - **`dims`** (integer): Embedding vector dimensions (must match your model)
  - **`embed`** (string): Embedding model in format `<provider>:<model-id>`
  - **`fields`** (list[str], optional): JSON fields to embed (default: `["$"]` for entire document)

See [Semantic Store](semantic-store.md) for more details.

## Environment Variables

You can override configuration using environment variables. See `.env.example` for a complete reference.

### Database

Two configuration modes are supported:

**Option 1: `DATABASE_URL`** (recommended for containerized/cloud deployments)

```bash
DATABASE_URL=postgresql://user:password@host:5432/aegra?sslmode=require
```

The URL is used directly by both SQLAlchemy (async) and LangGraph (sync) with the appropriate driver prefix applied automatically. Query parameters (e.g., `?sslmode=require`) are preserved.

**Option 2: Individual `POSTGRES_*` vars** (used when `DATABASE_URL` is not set)

```bash
POSTGRES_USER=aegra
POSTGRES_PASSWORD=secret
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=aegra
```

> **Note:** `DATABASE_URL` takes precedence. When set, individual `POSTGRES_*` vars are ignored for connection URLs.

### Other Variables

- **`AEGRA_CONFIG`**: Path to config file (overrides default resolution)
- **`OPENAI_API_KEY`**: OpenAI API key for LLM operations
- **`AUTH_TYPE`**: Authentication mode (`noop`, `custom`)
- **`LOG_LEVEL`**: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- **`ENV_MODE`**: Environment mode (`LOCAL`, `DEVELOPMENT`, `PRODUCTION`)

## Examples

### Minimal Configuration

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  }
}
```

### With Authentication

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "auth": {
    "path": "./jwt_mock_auth_example.py:auth"
  }
}
```

### With Custom Routes

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "http": {
    "app": "./custom_routes_example.py:app"
  }
}
```

### Production Configuration

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "auth": {
    "path": "./auth/production_auth.py:auth"
  },
  "http": {
    "app": "./custom_routes_example.py:app",
    "enable_custom_route_auth": true,
    "cors": {
      "allow_origins": ["https://myapp.com"],
      "allow_credentials": true
    }
  }
}
```

## Related Documentation

- [Authentication & Authorization](authentication.md) - Auth configuration details
- [Custom Routes](custom-routes.md) - HTTP and custom routes configuration
- [Semantic Store](semantic-store.md) - Store configuration details
- [Developer Guide](developer-guide.md) - Development setup
