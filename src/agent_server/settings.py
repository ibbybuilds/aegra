from typing import Annotated

from pydantic import BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_lower(v: str) -> str:
    """Converts to lowercase and strips whitespace."""
    return v.strip().lower() if isinstance(v, str) else v


def parse_upper(v: str) -> str:
    """Converts to uppercase and strips whitespace."""
    return v.strip().upper() if isinstance(v, str) else v


# Custom types for automatic formatting
LowerStr = Annotated[str, BeforeValidator(parse_lower)]
UpperStr = Annotated[str, BeforeValidator(parse_upper)]


class EnvBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(EnvBase):
    """General application settings."""

    PROJECT_NAME: str = "Aegra"
    VERSION: str = "0.1.0"

    # Server config
    HOST: str = "0.0.0.0"  # nosec B104
    PORT: int = 8000
    SERVER_URL: str = "http://localhost:8000"

    # App logic
    AEGRA_CONFIG: str
    AUTH_TYPE: LowerStr = "noop"
    ENV_MODE: UpperStr = "LOCAL"
    DEBUG: bool = False

    # Logging
    LOG_LEVEL: UpperStr = "INFO"
    LOG_VERBOSITY: LowerStr = "verbose"


class DatabaseSettings(EnvBase):
    """Database connection settings."""

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    DB_ECHO_LOG: bool = False

    @computed_field
    @property
    def database_url(self) -> str:
        """Async URL for SQLAlchemy (asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        """Sync URL for LangGraph/Psycopg (postgresql://)."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class PoolSettings(EnvBase):
    """Connection pool settings for SQLAlchemy and LangGraph."""

    SQLALCHEMY_POOL_SIZE: int = 2
    SQLALCHEMY_MAX_OVERFLOW: int = 0

    LANGGRAPH_MIN_POOL_SIZE: int = 1
    LANGGRAPH_MAX_POOL_SIZE: int = 6


class LangfuseSettings(EnvBase):
    """Langfuse integration settings."""

    LANGFUSE_LOGGING: bool


class Settings:
    def __init__(self):
        self.app = AppSettings()
        self.db = DatabaseSettings()
        self.pool = PoolSettings()
        self.langfuse = LangfuseSettings()


settings = Settings()
