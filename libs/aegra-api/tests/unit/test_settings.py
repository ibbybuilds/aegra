"""Tests for DatabaseSettings DATABASE_URL parsing."""

import pytest

from aegra_api.settings import DatabaseSettings


class TestDatabaseURLParsing:
    """Test that DATABASE_URL is correctly parsed into individual POSTGRES_* fields."""

    def test_defaults_when_no_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Individual defaults are used when DATABASE_URL is not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_PORT", raising=False)
        monkeypatch.delenv("POSTGRES_DB", raising=False)

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "postgres"
        assert db.POSTGRES_PASSWORD == "postgres"
        assert db.POSTGRES_HOST == "localhost"
        assert db.POSTGRES_PORT == "5432"
        assert db.POSTGRES_DB == "aegra"

    def test_database_url_overrides_individual_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL takes priority over individual POSTGRES_* vars."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://myuser:mypass@db.example.com:5433/mydb")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "myuser"
        assert db.POSTGRES_PASSWORD == "mypass"
        assert db.POSTGRES_HOST == "db.example.com"
        assert db.POSTGRES_PORT == "5433"
        assert db.POSTGRES_DB == "mydb"

    def test_database_url_with_asyncpg_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL with asyncpg driver prefix is parsed correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/testdb")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "user"
        assert db.POSTGRES_HOST == "host"
        assert db.POSTGRES_DB == "testdb"

    def test_database_url_with_percent_encoded_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Percent-encoded characters in DATABASE_URL are decoded."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:p%40ss%23word@host:5432/db")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_PASSWORD == "p@ss#word"

    def test_database_url_default_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL without port keeps the default."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_HOST == "host"
        assert db.POSTGRES_PORT == "5432"  # default preserved

    def test_computed_urls_use_parsed_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Computed database_url and database_url_sync use the parsed fields."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://rdsuser:rdspass@rds.aws.com:5432/prod")

        db = DatabaseSettings(_env_file=None)

        assert "rdsuser:rdspass@rds.aws.com:5432/prod" in db.database_url
        assert "rdsuser:rdspass@rds.aws.com:5432/prod" in db.database_url_sync
        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")

    def test_query_params_preserved_in_computed_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SSL and other query params from DATABASE_URL are preserved."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://user:pass@rds.aws.com:5432/prod?sslmode=require&connect_timeout=10",
        )

        db = DatabaseSettings(_env_file=None)

        assert "sslmode=require" in db.database_url
        assert "connect_timeout=10" in db.database_url
        assert "sslmode=require" in db.database_url_sync
        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")

    def test_driver_prefix_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Driver prefix is always normalized regardless of input."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")

        db = DatabaseSettings(_env_file=None)

        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")
        assert not db.database_url_sync.startswith("postgresql+")

    def test_individual_vars_still_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Individual POSTGRES_* vars work when DATABASE_URL is not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("POSTGRES_USER", "custom_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "custom_pass")
        monkeypatch.setenv("POSTGRES_HOST", "custom-host")
        monkeypatch.setenv("POSTGRES_PORT", "5555")
        monkeypatch.setenv("POSTGRES_DB", "custom_db")

        db = DatabaseSettings(_env_file=None)

        assert db.POSTGRES_USER == "custom_user"
        assert "custom_user:custom_pass@custom-host:5555/custom_db" in db.database_url

    def test_legacy_postgres_scheme_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Legacy postgres:// scheme (Heroku/Render) is normalized to postgresql://."""
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")

        db = DatabaseSettings(_env_file=None)

        assert db.database_url.startswith("postgresql+asyncpg://")
        assert db.database_url_sync.startswith("postgresql://")
        assert "user:pass@host:5432/db" in db.database_url

    def test_malformed_database_url_does_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Malformed DATABASE_URL doesn't crash — fields fall back to defaults where unparseable."""
        monkeypatch.setenv("DATABASE_URL", "not-a-url")

        db = DatabaseSettings(_env_file=None)

        # urlparse can't extract user/host/port, so defaults are preserved
        assert db.POSTGRES_USER == "postgres"
        assert db.POSTGRES_HOST == "localhost"
        assert db.POSTGRES_PORT == "5432"
