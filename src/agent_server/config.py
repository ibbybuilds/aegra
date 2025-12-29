"""Configuration management for Aegra HTTP settings"""

import json
import os
from pathlib import Path
from typing import TypedDict

import structlog

logger = structlog.get_logger(__name__)


class CorsConfig(TypedDict, total=False):
    """CORS configuration options"""

    allow_origins: list[str]
    allow_methods: list[str]
    allow_headers: list[str]
    allow_credentials: bool
    expose_headers: list[str]
    max_age: int


class HttpConfig(TypedDict, total=False):
    """HTTP configuration options for custom routes"""

    app: str
    """Import path for custom Starlette/FastAPI app to mount"""
    enable_custom_route_auth: bool
    """Apply Aegra authentication middleware to custom routes"""
    cors: CorsConfig | None
    """Custom CORS configuration"""


class StoreIndexConfig(TypedDict, total=False):
    """Configuration for vector embeddings in store.

    Enables semantic similarity search using pgvector.
    See: https://github.com/ibbybuilds/aegra/issues/104
    """

    dims: int
    """Embedding vector dimensions (e.g., 1536 for OpenAI text-embedding-3-small)"""
    embed: str
    """Embedding model in format '<provider>:<model-id>'
    Examples:
    - openai:text-embedding-3-small (1536 dims)
    - openai:text-embedding-3-large (3072 dims)
    - bedrock:amazon.titan-embed-text-v2:0 (1024 dims)
    - cohere:embed-english-v3.0 (1024 dims)
    """


class StoreConfig(TypedDict, total=False):
    """Store configuration options"""

    index: StoreIndexConfig | None
    """Vector index configuration for semantic search"""


def _resolve_config_path() -> Path | None:
    """Resolve config file path using the same logic as LangGraphService.

    Resolution order:
    1) AEGRA_CONFIG env var (absolute or relative path) - returned even if doesn't exist
    2) aegra.json in CWD
    3) langgraph.json in CWD (fallback)

    Returns:
        Path to config file or None if not found
    """
    # 1) Env var override - return even if doesn't exist (let caller handle error)
    env_path = os.getenv("AEGRA_CONFIG")
    if env_path:
        return Path(env_path)

    # 2) aegra.json if present
    aegra_path = Path("aegra.json")
    if aegra_path.exists():
        return aegra_path

    # 3) fallback to langgraph.json
    langgraph_path = Path("langgraph.json")
    if langgraph_path.exists():
        return langgraph_path

    return None


def load_config() -> dict | None:
    """Load full config file using the same resolution logic as LangGraphService.

    Returns:
        Full config dict or None if not found
    """
    config_path = _resolve_config_path()
    if not config_path:
        return None

    try:
        with config_path.open() as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load config from {config_path}: {e}")
        return None


def load_http_config() -> HttpConfig | None:
    """Load HTTP config from aegra.json or langgraph.json.

    Uses the same config resolution logic as LangGraphService to ensure consistency.

    Returns:
        HTTP configuration dict or None if not found
    """
    config = load_config()
    if config is None:
        return None

    http_config = config.get("http")
    if http_config:
        config_path = _resolve_config_path()
        logger.info(f"Loaded HTTP config from {config_path}")
        return http_config

    return None


def load_store_config() -> StoreConfig | None:
    """Load store config from aegra.json or langgraph.json.

    Uses the same config resolution logic as LangGraphService to ensure consistency.

    Returns:
        Store configuration dict or None if not found
    """
    config = load_config()
    if config is None:
        return None

    store_config = config.get("store")
    if store_config:
        config_path = _resolve_config_path()
        logger.info(f"Loaded store config from {config_path}")
        return store_config

    return None
