"""Unit tests for RedisManager"""

from unittest.mock import AsyncMock, patch

import pytest

from aegra_api.core.redis_manager import RedisManager


class TestRedisManager:
    """Test RedisManager lifecycle"""

    @pytest.mark.asyncio
    async def test_initialize_creates_pool_and_pings(self) -> None:
        """Test that initialize creates connection pool and verifies connectivity"""
        manager = RedisManager()

        mock_client = AsyncMock()
        mock_pool = AsyncMock()

        with (
            patch("aegra_api.core.redis_manager.aioredis.ConnectionPool") as mock_pool_cls,
            patch("aegra_api.core.redis_manager.aioredis.Redis", return_value=mock_client) as mock_redis_cls,
        ):
            mock_pool_cls.from_url.return_value = mock_pool

            await manager.initialize()

            mock_pool_cls.from_url.assert_called_once()
            mock_redis_cls.assert_called_once_with(connection_pool=mock_pool)
            mock_client.ping.assert_awaited_once()

        # Clean up
        manager._client = None
        manager._pool = None

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self) -> None:
        """Test that calling initialize twice doesn't create a second pool"""
        manager = RedisManager()
        manager._client = AsyncMock()  # Simulate already initialized

        with patch("aegra_api.core.redis_manager.aioredis.ConnectionPool") as mock_pool_cls:
            await manager.initialize()

            mock_pool_cls.from_url.assert_not_called()

        # Clean up
        manager._client = None

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """Test that close disposes of client and pool"""
        manager = RedisManager()
        mock_client = AsyncMock()
        mock_pool = AsyncMock()
        manager._client = mock_client
        manager._pool = mock_pool

        await manager.close()

        mock_client.aclose.assert_awaited_once()
        mock_pool.disconnect.assert_awaited_once()
        assert manager._client is None
        assert manager._pool is None

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self) -> None:
        """Test that close is safe when not initialized"""
        manager = RedisManager()

        # Should not raise
        await manager.close()

    def test_get_client_returns_client(self) -> None:
        """Test get_client returns the initialized client"""
        manager = RedisManager()
        mock_client = AsyncMock()
        manager._client = mock_client

        result = manager.get_client()

        assert result is mock_client

        # Clean up
        manager._client = None

    def test_get_client_raises_when_not_initialized(self) -> None:
        """Test get_client raises RuntimeError when not initialized"""
        manager = RedisManager()

        with pytest.raises(RuntimeError, match="Redis not initialized"):
            manager.get_client()
