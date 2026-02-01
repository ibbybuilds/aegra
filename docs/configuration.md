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
AEGRA_CONFIG=production.json python run_server.py

# Use default aegra.json
python run_server.py
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
      "embedding_model": "text-embedding-3-small",
      "embedding_dimension": 1536
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
  - **`allow_credentials`**: Allow credentials in CORS requests (default: `false`)

See [Custom Routes](custom-routes.md) for more details.

## Store Configuration

Configure semantic store (vector embeddings):

```json
{
  "store": {
    "index": {
      "embedding_model": "text-embedding-3-small",
      "embedding_dimension": 1536
    }
  }
}
```

### Options

- **`index`** (optional): Vector index configuration
  - **`embedding_model`**: Model name for embeddings (default: `"text-embedding-3-small"`)
  - **`embedding_dimension`**: Dimension of embeddings (default: `1536`)

See [Semantic Store](semantic-store.md) for more details.

## Environment Variables

You can override configuration using environment variables:

- **`AEGRA_CONFIG`**: Path to config file (overrides default resolution)
- **`DATABASE_URL`**: PostgreSQL connection string
- **`OPENAI_API_KEY`**: OpenAI API key for LLM operations

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
