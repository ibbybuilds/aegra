"""Redis client utility module for connection pooling and helper functions."""

import gzip
import json
import os
from typing import Any

import redis.asyncio as redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration from environment
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Global connection pool (singleton)
_redis_pool: redis.ConnectionPool | None = None
_redis_client: redis.Redis | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """Get or create the Redis connection pool.

    Returns:
        Redis connection pool instance
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True,  # Automatically decode bytes to strings
            max_connections=10,
        )
    return _redis_pool


def get_redis_client() -> redis.Redis:
    """Get or create the Redis client using the connection pool.

    Returns:
        Redis client instance
    """
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = redis.Redis(connection_pool=pool)
    return _redis_client


async def redis_get_json(key: str) -> dict[str, Any] | None:
    """Get a JSON value from Redis.

    Args:
        key: Redis key

    Returns:
        Parsed JSON dict if key exists, None otherwise
    """
    try:
        client = get_redis_client()
        value = await client.get(key)
        if value is None:
            return None
        return json.loads(value)
    except (redis.RedisError, json.JSONDecodeError) as e:
        print(f"Redis get error for key {key}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error getting key {key}: {e}")
        return None


async def redis_set_json(
    key: str, value: dict[str, Any], ttl_seconds: int | None = None
) -> bool:
    """Set a JSON value in Redis with optional TTL.

    Args:
        key: Redis key
        value: Dictionary to store as JSON
        ttl_seconds: Optional TTL in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_redis_client()
        json_value = json.dumps(value)
        if ttl_seconds:
            await client.setex(key, ttl_seconds, json_value)
        else:
            await client.set(key, json_value)
        return True
    except (redis.RedisError, json.JSONEncodeError) as e:
        print(f"Redis set error for key {key}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error setting key {key}: {e}")
        return False


async def redis_exists(key: str) -> bool:
    """Check if a key exists in Redis.

    Args:
        key: Redis key

    Returns:
        True if key exists, False otherwise
    """
    try:
        client = get_redis_client()
        result = await client.exists(key)
        return result > 0
    except redis.RedisError as e:
        print(f"Redis exists error for key {key}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error checking key {key}: {e}")
        return False


async def redis_get_json_compressed(key: str) -> dict[str, Any] | None:
    """Get a compressed JSON value from Redis.

    Args:
        key: Redis key

    Returns:
        Parsed JSON dict if key exists, None otherwise
    """
    try:
        # Need a client with decode_responses=False for binary data
        pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=False,  # Keep as bytes for decompression
            max_connections=10,
        )
        binary_client = redis.Redis(connection_pool=pool)

        compressed_value = await binary_client.get(key)
        await pool.disconnect()

        if compressed_value is None:
            return None

        # Decompress and parse JSON
        json_bytes = gzip.decompress(compressed_value)
        return json.loads(json_bytes.decode("utf-8"))
    except (redis.RedisError, gzip.BadGzipFile, json.JSONDecodeError) as e:
        print(f"Redis get compressed error for key {key}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error getting compressed key {key}: {e}")
        return None


async def redis_set_json_compressed(
    key: str, value: dict[str, Any], ttl_seconds: int | None = None
) -> bool:
    """Set a compressed JSON value in Redis with optional TTL.

    Compresses JSON data with gzip before storing to reduce memory usage.
    Typical compression ratio: 70-90% for JSON data.

    Args:
        key: Redis key
        value: Dictionary to store as compressed JSON
        ttl_seconds: Optional TTL in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        # Need a client with decode_responses=False for binary data
        pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=False,  # Store as bytes
            max_connections=10,
        )
        binary_client = redis.Redis(connection_pool=pool)

        # Serialize to JSON and compress
        json_bytes = json.dumps(value).encode("utf-8")
        compressed_value = gzip.compress(
            json_bytes, compresslevel=6
        )  # Balanced speed/ratio

        if ttl_seconds:
            await binary_client.setex(key, ttl_seconds, compressed_value)
        else:
            await binary_client.set(key, compressed_value)

        await pool.disconnect()
        return True
    except (redis.RedisError, gzip.BadGzipFile, json.JSONEncodeError) as e:
        print(f"Redis set compressed error for key {key}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error setting compressed key {key}: {e}")
        return False


async def close_redis_pool():
    """Close the Redis connection pool (call on application shutdown)."""
    global _redis_pool, _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
