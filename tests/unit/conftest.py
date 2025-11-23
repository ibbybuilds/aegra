"""Unit test specific fixtures

Unit tests should be fast and isolated, with no external dependencies.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_observability_manager():
    """Reset the global observability manager before each test.

    This ensures tests don't interfere with each other when they reload
    modules that create and register observability providers.
    """
    from src.agent_server.observability.base import get_observability_manager

    manager = get_observability_manager()
    # Clear all registered providers before each test
    manager._providers.clear()
    yield
    # Clean up after test
    manager._providers.clear()
