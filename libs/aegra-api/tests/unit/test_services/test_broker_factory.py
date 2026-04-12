"""Unit tests for broker factory selection"""

from unittest.mock import patch

from aegra_api.services.broker import BrokerManager, _create_broker_manager
from aegra_api.services.redis_broker import RedisBrokerManager


class TestBrokerFactory:
    """Test _create_broker_manager factory function"""

    def test_returns_in_memory_broker_when_redis_disabled(self) -> None:
        with patch("aegra_api.services.broker.settings") as mock_settings:
            mock_settings.redis.REDIS_BROKER_ENABLED = False

            manager = _create_broker_manager()

            assert isinstance(manager, BrokerManager)

    def test_returns_redis_broker_when_redis_enabled(self) -> None:
        with patch("aegra_api.services.broker.settings") as mock_settings:
            mock_settings.redis.REDIS_BROKER_ENABLED = True

            manager = _create_broker_manager()

            assert isinstance(manager, RedisBrokerManager)
