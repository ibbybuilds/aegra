# Custom Routes

Aegra supports adding custom FastAPI endpoints to extend your server with additional functionality. This is useful for webhooks, admin panels, custom UI, or any other endpoints you need.

## Configuration

Add custom routes by configuring the `http.app` field in your `aegra.json` or `langgraph.json`:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "http": {
    "app": "./custom_routes.py:app",
    "enable_custom_route_auth": false,
    "cors": {
      "allow_origins": ["https://example.com"],
      "allow_credentials": true
    }
  }
}
```

## Creating Custom Routes

Create a Python file (e.g., `custom_routes.py`) with your FastAPI app:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/custom/hello")
async def hello():
    return {"message": "Hello from custom route!"}

@app.post("/custom/webhook")
async def webhook(data: dict):
    return {"received": data, "status": "processed"}

# You can override shadowable routes like the root
@app.get("/")
async def custom_root():
    return {"message": "Custom Aegra Server", "custom": True}
```

## Route Priority

Custom routes follow this priority order:

1. **Unshadowable routes**: `/health`, `/ready`, `/live`, `/docs`, `/openapi.json` - always accessible
2. **Custom user routes**: Your endpoints take precedence
3. **Shadowable routes**: `/`, `/info` - can be overridden by custom routes
4. **Protected core routes**: `/assistants`, `/threads`, `/runs`, `/store` - cannot be overridden

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `app` | `string` | `None` | Import path to custom FastAPI/Starlette app (format: `"path/to/file.py:variable"`) |
| `enable_custom_route_auth` | `boolean` | `false` | Apply Aegra's authentication middleware to custom routes |
| `cors` | `object` | `None` | Custom CORS configuration |

## Use Cases

- **Webhooks**: Add endpoints to receive external webhooks
- **Admin Panel**: Build custom admin interfaces
- **Custom UI**: Serve additional frontend applications
- **Metrics**: Add custom monitoring endpoints
- **Integration**: Connect with third-party services

## Example

See [`custom_routes_example.py`](../custom_routes_example.py) in the project root for a complete example.
