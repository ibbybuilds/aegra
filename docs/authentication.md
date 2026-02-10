# Authentication & Authorization

Aegra supports flexible authentication and authorization through configurable auth handlers. You can implement JWT, OAuth, Firebase, or any custom authentication system.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [Authorization Handlers](#authorization-handlers)
- [Examples](#examples)
- [Custom Routes](#custom-routes)
- [Testing](#testing)

## Quick Start

1. **Create an auth file** (e.g., `my_auth.py`):

```python
from langgraph_sdk import Auth

auth = Auth()

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    # Your authentication logic
    token = headers.get("Authorization", "").replace("Bearer ", "")
    # Verify token and return user data
    return {
        "identity": "user123",
        "display_name": "John Doe",
        "permissions": ["read", "write"],
        "is_authenticated": True
    }
```

2. **Add auth to your config** (`aegra.json`):

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  },
  "auth": {
    "path": "./my_auth.py:auth"
  }
}
```

3. **Start the server**:

```bash
aegra dev
# OR with Docker:
docker compose up
```

That's it! All API endpoints now require authentication.

## Configuration

Authentication is configured in your `aegra.json` (or `langgraph.json`) file:

```json
{
  "auth": {
    "path": "./my_auth.py:auth",
    "disable_studio_auth": false
  }
}
```

### Configuration Options

- **`path`** (required): Import path to your auth handler
  - Format: `'./file.py:variable'` or `'module:variable'`
  - Examples:
    - `'./auth.py:auth'` - Load `auth` from `auth.py` in project root
    - `'./src/auth/jwt.py:auth'` - Load from nested path
    - `'mypackage.auth:auth'` - Load from installed package

- **`disable_studio_auth`** (optional, default: `false`): Disable authentication for LangGraph Studio connections

### Config File Resolution

Aegra resolves config files in this order:

1. `AEGRA_CONFIG` environment variable (if set)
2. `aegra.json` in current working directory
3. `langgraph.json` in current working directory (fallback for compatibility)

Example:

```bash
# Use custom config file
AEGRA_CONFIG=production.json aegra dev
```

## Authentication

Authentication is handled by the `@auth.authenticate` decorator in your auth file.

### Basic Example

```python
from langgraph_sdk import Auth

auth = Auth()

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    """Authenticate request and return user data."""
    # Extract token from headers
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Exception("Missing or invalid Authorization header")

    token = auth_header.replace("Bearer ", "")

    # Verify token (your logic here)
    # For JWT: verify signature, check expiration, etc.
    # For OAuth: validate access token
    # For Firebase: verify ID token

    # Return user data
    return {
        "identity": "user123",           # Required: unique user identifier
        "display_name": "John Doe",      # Optional: display name
        "permissions": ["read", "write"], # Optional: list of permissions
        "is_authenticated": True,        # Optional: authentication status

        # Custom fields are preserved and accessible in routes
        "role": "admin",
        "team_id": "team456",
        "subscription_tier": "premium"
    }
```

### User Data Fields

The authentication handler must return a dictionary with at least:

- **`identity`** (required): Unique user identifier (string)
- **`display_name`** (optional): User's display name (defaults to `identity`)
- **`permissions`** (optional): List of permission strings
- **`is_authenticated`** (optional): Boolean (defaults to `True`)

Any additional fields are preserved and accessible in your routes via the `User` model.

### Error Handling

Raise an exception to deny authentication:

```python
@auth.authenticate
async def authenticate(headers: dict) -> dict:
    token = headers.get("Authorization", "").replace("Bearer ", "")

    if not token:
        raise Exception("Authentication required")

    # Verify token
    if not is_valid_token(token):
        raise Exception("Invalid token")

    return user_data
```

## Authorization Handlers

Authorization handlers (`@auth.on.*`) provide fine-grained access control for specific resources and actions.

### Handler Types

Authorization handlers can:

1. **Allow** (default): Return `None` or `True`
2. **Deny**: Return `False` (returns 403 Forbidden)
3. **Filter**: Return a dictionary with filters to apply
4. **Modify**: Modify the `value` dict (e.g., inject metadata)

### Handler Resolution Priority

Handlers are resolved in order of specificity (most specific first):

1. **Resource + Action**: `@auth.on.threads.create`
2. **Resource**: `@auth.on.threads`
3. **Action**: `@auth.on.*.create`
4. **Global**: `@auth.on`

### Basic Examples

#### Allow/Deny Access

```python
@auth.on.assistants.delete
async def restrict_deletion(ctx, value):
    """Only admins can delete assistants."""
    if ctx.user.role != "admin":
        return False  # Deny access
    return None  # Allow access
```

#### Inject Metadata

```python
@auth.on.threads.create
async def inject_team_id(ctx, value):
    """Inject team_id into thread metadata."""
    if "metadata" not in value:
        value["metadata"] = {}
    value["metadata"]["team_id"] = ctx.user.team_id
    return value  # Return modified value
```

#### Apply Filters

```python
@auth.on.threads.search
async def filter_by_team(ctx, value):
    """Filter threads by user's team."""
    return {
        "metadata": {"team_id": ctx.user.team_id}
    }
```

### Handler Context

The `ctx` parameter provides:

- **`ctx.user`**: Authenticated user object
- **`ctx.resource`**: Resource name (e.g., "threads", "assistants")
- **`ctx.action`**: Action name (e.g., "create", "read", "update")
- **`ctx.permissions`**: User permissions list

### Handler Return Values

| Return Value | Behavior |
|-------------|----------|
| `None` or `True` | Allow request, no filters |
| `False` | Deny request (403 Forbidden) |
| `dict` | Allow with filters applied (e.g., `{"metadata": {"team_id": "123"}}`) |
| Modified `value` | Allow with modified request data |

### Non-Interruptive Design

Authorization handlers are **non-interruptive by default**:

- If no auth is configured → requests are allowed
- If no handlers are defined → requests are allowed
- Handlers are purely additive unless explicitly denying

This ensures Aegra works out-of-the-box without requiring authorization handlers.

## Examples

### Complete JWT Example

See [`jwt_mock_auth_example.py`](../jwt_mock_auth_example.py) for a complete example including:

- JWT token parsing
- User data extraction
- Multiple authorization handlers
- Team-based filtering
- Role-based access control
- Metadata injection

### OAuth Example

```python
from langgraph_sdk import Auth
import httpx

auth = Auth()

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    """OAuth authentication."""
    token = headers.get("Authorization", "").replace("Bearer ", "")

    # Verify token with OAuth provider
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://oauth-provider.com/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        user_info = response.json()

    return {
        "identity": user_info["sub"],
        "display_name": user_info["name"],
        "permissions": user_info.get("permissions", []),
        "email": user_info["email"]
    }
```

### Firebase Example

```python
from langgraph_sdk import Auth
from firebase_admin import auth as firebase_auth

auth = Auth()

@auth.authenticate
async def authenticate(headers: dict) -> dict:
    """Firebase authentication."""
    token = headers.get("Authorization", "").replace("Bearer ", "")

    # Verify Firebase ID token
    decoded_token = firebase_auth.verify_id_token(token)

    return {
        "identity": decoded_token["uid"],
        "display_name": decoded_token.get("name", ""),
        "permissions": decoded_token.get("permissions", []),
        "email": decoded_token.get("email", "")
    }
```

## Custom Routes

Custom routes can use authentication via the `require_auth` dependency:

```python
from fastapi import Depends
from aegra_api.core.auth_deps import require_auth
from aegra_api.models.auth import User

@app.get("/custom/whoami")
async def whoami(user: User = Depends(require_auth)):
    """Return current user info."""
    return {
        "identity": user.identity,
        "display_name": user.display_name,
        "permissions": user.permissions,
        # Custom fields are accessible
        "role": user.role,
        "team_id": user.team_id
    }
```

### Enabling Auth for Custom Routes

By default, custom routes don't require authentication unless you explicitly use `require_auth`. To enable auth for all custom routes:

```json
{
  "http": {
    "app": "./custom_routes_example.py:app",
    "enable_custom_route_auth": true
  }
}
```

When `enable_custom_route_auth` is `true`, all custom routes require authentication unless explicitly marked as public.

## Testing

### Manual Auth Tests

Auth tests are located in `tests/e2e/manual_auth_tests/` and are skipped by default. To run them:

1. **Create an auth config file**:

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

2. **Start server with auth**:

```bash
AEGRA_CONFIG=my_auth_config.json aegra dev
```

3. **Run auth tests**:

```bash
pytest tests/e2e/manual_auth_tests/ -v -m manual_auth
```

See [`tests/e2e/manual_auth_tests/README.md`](../tests/e2e/manual_auth_tests/README.md) for more details.

## No-Auth Mode

If no auth is configured, Aegra runs in **no-auth mode**:

- All requests are allowed
- User is set to `anonymous`
- Authorization handlers are not called

This ensures Aegra works out-of-the-box for development and testing.

## Best Practices

1. **Keep auth logic separate**: Create a dedicated auth file/module
2. **Use environment variables**: Store secrets in environment variables, not in code
3. **Validate tokens properly**: Always verify token signatures and expiration
4. **Handle errors gracefully**: Return clear error messages for authentication failures
5. **Test thoroughly**: Use the manual auth tests to verify your implementation

## Related Documentation

- [Custom Routes](custom-routes.md) - Adding custom endpoints with auth
- [Developer Guide](developer-guide.md) - Development setup and workflow
- [JWT Mock Auth Example](../jwt_mock_auth_example.py) - Complete example implementation
