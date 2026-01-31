# Authorization Handlers Implementation

## Summary

This PR implements comprehensive authorization handler support for Aegra, allowing users to define fine-grained access control rules using `@auth.on.*` decorators. The implementation follows a non-interruptive design philosophy, ensuring Aegra works out-of-the-box without requiring authorization handlers.

## Key Features

### 🎯 Authorization Handlers (`@auth.on.*`)

- **Priority-based handler resolution**: Most specific handlers take precedence
  - Resource+action specific (e.g., `@auth.on.threads.create`)
  - Resource-specific (e.g., `@auth.on.threads`)
  - Action-specific (e.g., `@auth.on.*.create`)
  - Global handler (`@auth.on`)

- **Handler return types**:
  - `None` or `True`: Allow request
  - `False`: Deny request (403)
  - `dict`: Allow with filters applied (e.g., `{"team_id": "team123"}`)

- **Non-interruptive by default**: 
  - No auth configured → allows by default
  - No handlers defined → allows by default
  - Handlers are purely additive unless explicitly denying

### 🔐 API Integration

Authorization handlers are integrated into all core API endpoints:
- **Assistants**: Create, read, update, delete, search
- **Threads**: Create, read, update, search, state management
- **Runs**: Create, read, list, wait
- **Store**: Create, read, update, delete, search

Handlers can:
- Inject metadata (e.g., `team_id`, `created_by`)
- Apply filters to queries (e.g., user-scoped access)
- Deny access based on permissions
- Modify request data before processing

### 🧪 Testing

- **Unit tests**: 19 tests covering handler resolution, context building, and error handling
- **Integration tests**: Comprehensive auth flow and handler integration tests
- **E2E tests**: Moved to `manual_auth_tests/` directory (skipped by default)
  - Tests are marked with `manual_auth` marker
  - Can be run explicitly: `pytest -m manual_auth`
  - See `tests/e2e/manual_auth_tests/README.md` for details

### 📝 Examples

See `jwt_mock_auth_example.py` for a complete example including:
- JWT authentication
- Authorization handlers for threads, assistants, and store
- Team-based filtering
- Role-based access control

## Changes

### Core Implementation
- `src/agent_server/core/auth_handlers.py`: Authorization handler resolution and execution
- `src/agent_server/core/auth_middleware.py`: Improved auth middleware with reduced log noise
- `src/agent_server/core/auth_deps.py`: Enhanced auth dependencies
- `src/agent_server/core/auth_ctx.py`: Auth context helpers

### API Updates
- `src/agent_server/api/assistants.py`: Authorization checks for assistant operations
- `src/agent_server/api/threads.py`: Authorization checks for thread operations
- `src/agent_server/api/runs.py`: Authorization checks for run operations
- `src/agent_server/api/store.py`: Authorization checks for store operations

### Configuration & Examples
- `jwt_mock_auth_example.py`: Complete JWT auth example with authorization handlers
- `custom_routes_example.py`: Simplified custom routes example
- `aegra.json`: Removed auth config (users create their own)

### Testing
- `tests/unit/test_core/test_auth_handlers.py`: Unit tests for authorization handlers
- `tests/integration/test_auth_handlers_integration.py`: Integration tests
- `tests/e2e/manual_auth_tests/`: Manual E2E tests (skipped by default)

## Breaking Changes

None. This is a purely additive feature. Existing code continues to work without modification.

## Migration Guide

To use authorization handlers:

1. Create an auth file (e.g., `my_auth.py`):
```python
from langgraph_sdk import Auth

auth = Auth()

@auth.authenticate
async def authenticate(request):
    # Your auth logic
    return user_dict

@auth.on.threads.create
async def inject_team_id(ctx, value):
    # Inject team_id into metadata
    value.setdefault("metadata", {})["team_id"] = ctx.user.team_id
    return value
```

2. Create a config file with auth:
```json
{
  "auth": {
    "path": "./my_auth.py:auth"
  }
}
```

3. Start server with config:
```bash
AEGRA_CONFIG=my_config.json python run_server.py
```

## Testing

All tests pass:
- ✅ 755+ unit tests
- ✅ 755+ integration tests  
- ✅ 51 E2E tests (21 manual auth tests skipped by default)

Run manual auth tests:
```bash
# Start server with auth enabled
AEGRA_CONFIG=my_auth_config.json python run_server.py

# Run manual auth tests
pytest tests/e2e/manual_auth_tests/ -v -m manual_auth
```

## Documentation

- `docs/authentication.md`: Complete authentication and authorization guide
- `docs/configuration.md`: Configuration reference for aegra.json
- `tests/e2e/manual_auth_tests/README.md`: Guide for running manual auth tests
- `jwt_mock_auth_example.py`: Complete example implementation

Documentation includes:
- Quick start guide for authentication
- Configuration options for `aegra.json`
- Authorization handler examples
- JWT, OAuth, and Firebase examples
- Custom routes integration
- Testing guide

## Related Issues & PRs

Closes #152 - Configurable Auth File Loading from aegra.json
Closes #151 - Flexible User Model - Accept Arbitrary Fields Without Type Errors

**Note on PR #150**: This PR's base commit (8059de1) already includes the OpenAPI fix for core routes appearing in API spec when using custom routes. The fix uses `_include_core_routers()` to directly include routers (cleaner approach) rather than PR #150's `merge_routes()` + `update_openapi_spec()` approach. Both solve the same problem, but this PR's approach is already merged.

This PR implements authorization handler support as part of the auth and OpenAPI refactor.
