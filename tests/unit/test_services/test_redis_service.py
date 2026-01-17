"""Unit tests for RedisService"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent_server.services.redis_service import RedisService


class TestRedisService:
    @pytest.mark.asyncio
    async def test_initialize_disabled(self):
        """Test initialize when disabled"""
        with patch("src.agent_server.services.redis_service.settings") as mock_settings:
            mock_settings.redis.REDIS_ENABLED = False

            service = RedisService()
            await service.initialize()

            assert service.redis is None
            assert not service.enabled

    @pytest.mark.asyncio
    async def test_initialize_enabled_no_url(self):
        """Test initialize when enabled but no URL"""
        with patch("src.agent_server.services.redis_service.settings") as mock_settings:
            mock_settings.redis.REDIS_ENABLED = True
            mock_settings.redis.REDIS_URL = None

            service = RedisService()
            await service.initialize()

            assert service.redis is None
            assert not service.enabled

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful initialization"""
        with (
            patch("src.agent_server.services.redis_service.settings") as mock_settings,
            patch(
                "src.agent_server.services.redis_service.aioredis.from_url"
            ) as mock_redis_cls,
        ):
            mock_settings.redis.REDIS_ENABLED = True
            mock_settings.redis.REDIS_URL = "redis://localhost"
            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            service = RedisService()
            await service.initialize()

            assert service.redis is mock_redis
            assert service.enabled
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_connection_fail(self):
        """Test initialization failure"""
        with (
            patch("src.agent_server.services.redis_service.settings") as mock_settings,
            patch(
                "src.agent_server.services.redis_service.aioredis.from_url"
            ) as mock_redis_cls,
        ):
            mock_settings.redis.REDIS_ENABLED = True
            mock_settings.redis.REDIS_URL = "redis://localhost"
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = Exception("Connection fail")
            mock_redis_cls.return_value = mock_redis

            service = RedisService()
            await service.initialize()

            # Should disable itself on failure
            assert not service.enabled

    @pytest.mark.asyncio
    async def test_get_not_enabled(self):
        """Test get when not enabled"""
        service = RedisService()
        service.enabled = False
        result = await service.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_success(self):
        """Test successful get"""
        service = RedisService()
        service.enabled = True
        service.redis = AsyncMock()
        service.redis.get.return_value = '{"foo": "bar"}'

        result = await service.get("key")
        assert result == {"foo": "bar"}
        service.redis.get.assert_called_with("key")

    @pytest.mark.asyncio
    async def test_set_success(self):
        """Test successful set"""
        service = RedisService()
        service.enabled = True
        service.redis = AsyncMock()
        service.ttl = 60

        result = await service.set("key", {"foo": "bar"})

        assert result is True
        service.redis.set.assert_called_with("key", '{"foo": "bar"}', ex=60)

    @pytest.mark.asyncio
    async def test_push_stream_success(self):
        """Test successful push to stream"""
        service = RedisService()
        service.enabled = True
        service.redis = AsyncMock()
        service.redis.xadd.return_value = "1-0"

        result = await service.push_stream("stream-key", {"data": "test"})

        assert result == "1-0"
        service.redis.xadd.assert_called_with(
            "stream-key", {"data": '{"data": "test"}'}
        )
