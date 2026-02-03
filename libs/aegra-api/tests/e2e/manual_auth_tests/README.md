# Manual Auth Tests

**⚠️ These tests are skipped by default and should only be run when making changes to authentication/authorization code.**

## Purpose

These tests verify the authentication and authorization functionality of Aegra. Since Aegra is designed to be a package where users implement their own auth, these tests are not part of the regular test suite.

## When to Run These Tests

Run these tests when:
- Making changes to `src/agent_server/core/auth_middleware.py`
- Making changes to `src/agent_server/core/auth_handlers.py`
- Making changes to `src/agent_server/core/auth_deps.py`
- Making changes to authorization handler resolution logic
- Adding new authentication features
- Fixing authentication-related bugs

## How to Run

1. **Create an auth config file** (e.g., `my_auth_config.json`):
   ```json
   {
     "graphs": {
       "agent": "./graphs/react_agent/graph.py:graph"
     },
     "auth": {
       "path": "./jwt_mock_auth_example.py:auth"
     },
     "http": {
       "app": "./custom_routes_example.py:app",
       "enable_custom_route_auth": false
     }
   }
   ```

2. **Start the server with auth enabled:**
   ```bash
   AEGRA_CONFIG=my_auth_config.json python run_server.py
   # OR for Docker:
   AEGRA_CONFIG=my_auth_config.json docker compose up
   ```

3. **Run the manual auth tests:**
   ```bash
   # Run all manual auth tests
   pytest tests/e2e/manual_auth_tests/ -v -m manual_auth

   # Run specific test file
   pytest tests/e2e/manual_auth_tests/test_auth_e2e.py -v -m manual_auth
   pytest tests/e2e/manual_auth_tests/test_authorization_handlers_e2e.py -v -m manual_auth
   ```

## Test Files

- `test_auth_e2e.py` - Core authentication flow tests (JWT, custom routes, error handling)
- `test_authorization_handlers_e2e.py` - Authorization handler tests (@auth.on.* decorators)

## Notes

- These tests require a server running with auth enabled (create your own config file)
- Tests will automatically skip if the server doesn't have auth enabled
- These tests use the mock JWT auth from `jwt_mock_auth_example.py`
- Since auth is user-specific, these tests are manual and not part of CI
