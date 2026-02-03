"""Pytest configuration for manual auth E2E tests.

⚠️ These tests are skipped by default (via pytest.ini -m "not manual_auth").
Run them explicitly when making auth changes: pytest -m manual_auth

This conftest.py skips auth flow tests if the server doesn't have auth enabled.

The server loads config at startup, so it must be started with a config file
that includes auth configuration:
    AEGRA_CONFIG=my_auth_config.json python run_server.py
    OR: AEGRA_CONFIG=my_auth_config.json docker compose up

Create your own config file with auth.path pointing to your auth implementation.
See tests/e2e/manual_auth_tests/README.md for details.

If auth is not enabled, tests are skipped with a helpful message.
"""

import pytest

from aegra_api.settings import settings
from tests.e2e._utils import check_server_has_auth


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_auth():
    """Skip auth flow tests if server doesn't have auth enabled.

    This fixture automatically skips all tests in test_auth_flow if:
    - Server is not running
    - Server doesn't have auth enabled

    This allows regular E2E tests to run without auth, while auth tests
    are skipped unless the server is configured with auth.
    """
    server_url = settings.app.SERVER_URL

    # Check if server has auth enabled
    has_auth = check_server_has_auth(server_url)

    if has_auth is False:
        pytest.skip(
            "Server is running but does not have auth enabled. "
            "Create a config file with auth.path and start server with: "
            "AEGRA_CONFIG=my_auth_config.json python run_server.py"
        )
    elif has_auth is None:
        pytest.skip(
            f"Could not connect to server at {server_url} or determine auth status. "
            "Make sure server is running and started with a config file that includes auth."
        )
    # If has_auth is True, continue with tests
