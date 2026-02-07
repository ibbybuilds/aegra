"""Database fixtures for tests"""

from collections.abc import AsyncIterator, Callable


class DummySessionBase:
    """Minimal emulation of SQLAlchemy AsyncSession for testing

    Override scalar/scalars/commit/refresh in subclasses/fixtures to return
    appropriate rows for a test. By default, returns empty data.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, _):
        """AsyncSession.add is sync in SQLAlchemy"""
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def scalar(self, _stmt):
        return None

    async def scalars(self, _stmt):
        class Result:
            def all(self_inner):
                return []

        return Result()


def override_get_session_dep(
    session_factory: Callable[[], DummySessionBase],
) -> Callable[[], AsyncIterator[DummySessionBase]]:
    """Create a dependency override for get_session"""

    async def _dep():
        yield session_factory()

    return _dep
