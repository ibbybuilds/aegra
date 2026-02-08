"""E2E test specific fixtures

E2E tests use the full system with real database and services.

Note: Auth tests have been moved to tests/e2e/manual_auth_tests/ and are
skipped by default via pytest.ini. They can be run explicitly with: pytest -m manual_auth
"""
