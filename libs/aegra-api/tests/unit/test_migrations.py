"""Tests for aegra_api.core.migrations module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from aegra_api.core.migrations import find_alembic_ini, get_alembic_config


class TestFindAlembicIni:
    """Tests for find_alembic_ini() resolution order."""

    def test_finds_alembic_ini_in_cwd(self, tmp_path, monkeypatch):
        """Should find alembic.ini when it exists in CWD."""
        monkeypatch.chdir(tmp_path)
        ini_file = tmp_path / "alembic.ini"
        ini_file.write_text("[alembic]\nscript_location = alembic\n")

        result = find_alembic_ini()
        assert result == ini_file.resolve()

    def test_finds_alembic_ini_in_package(self, tmp_path, monkeypatch):
        """Should find alembic.ini bundled with the aegra_api package."""
        # CWD has no alembic.ini
        monkeypatch.chdir(tmp_path)

        # The package directory should have alembic.ini (from force-include)
        # We verify it finds the file relative to migrations.py's parent.parent
        result = find_alembic_ini()
        # Should be in the package directory (aegra_api/)
        assert result.name == "alembic.ini"
        assert result.exists()

    def test_cwd_takes_priority_over_package(self, tmp_path, monkeypatch):
        """CWD alembic.ini should be preferred over package-bundled one."""
        monkeypatch.chdir(tmp_path)
        cwd_ini = tmp_path / "alembic.ini"
        cwd_ini.write_text("[alembic]\nscript_location = alembic\n")

        result = find_alembic_ini()
        # Should be the CWD file, not the package file
        assert result == cwd_ini.resolve()

    def test_raises_when_not_found(self, tmp_path, monkeypatch):
        """Should raise FileNotFoundError when alembic.ini is nowhere."""
        monkeypatch.chdir(tmp_path)

        # Create a fake module location where no alembic.ini exists
        # at any resolution level (CWD, package dir, or dev layout)
        fake_core = tmp_path / "fake" / "pkg" / "core"
        fake_core.mkdir(parents=True)
        (fake_core / "migrations.py").touch()

        import aegra_api.core.migrations as migrations_mod

        monkeypatch.setattr(
            migrations_mod,
            "__file__",
            str(fake_core / "migrations.py"),
        )

        with pytest.raises(FileNotFoundError, match="Could not find alembic.ini"):
            find_alembic_ini()


class TestGetAlembicConfig:
    """Tests for get_alembic_config()."""

    def test_returns_config_object(self, tmp_path, monkeypatch):
        """Should return a valid Alembic Config object."""
        monkeypatch.chdir(tmp_path)

        # Create a minimal alembic.ini
        ini_file = tmp_path / "alembic.ini"
        ini_file.write_text("[alembic]\nscript_location = alembic\n")

        # Create the alembic directory
        alembic_dir = tmp_path / "alembic"
        alembic_dir.mkdir()

        cfg = get_alembic_config()
        assert cfg is not None

        # script_location should be resolved to absolute path
        script_loc = cfg.get_main_option("script_location")
        assert Path(script_loc).is_absolute()
        assert script_loc == str(alembic_dir.resolve())

    def test_resolves_relative_script_location(self, tmp_path, monkeypatch):
        """Should resolve relative script_location to absolute path."""
        monkeypatch.chdir(tmp_path)

        ini_file = tmp_path / "alembic.ini"
        ini_file.write_text("[alembic]\nscript_location = alembic\n")

        alembic_dir = tmp_path / "alembic"
        alembic_dir.mkdir()

        cfg = get_alembic_config()
        script_loc = cfg.get_main_option("script_location")
        assert Path(script_loc).is_absolute()

    def test_preserves_absolute_script_location(self, tmp_path, monkeypatch):
        """Should not modify an already-absolute script_location."""
        monkeypatch.chdir(tmp_path)

        abs_path = str(tmp_path / "my_alembic")
        ini_file = tmp_path / "alembic.ini"
        ini_file.write_text(f"[alembic]\nscript_location = {abs_path}\n")

        cfg = get_alembic_config()
        assert cfg.get_main_option("script_location") == abs_path


class TestRunMigrations:
    """Tests for run_migrations() and run_migrations_async()."""

    def test_run_migrations_calls_alembic_upgrade(self, tmp_path, monkeypatch):
        """Should call alembic command.upgrade with 'head'."""
        monkeypatch.chdir(tmp_path)

        ini_file = tmp_path / "alembic.ini"
        ini_file.write_text("[alembic]\nscript_location = alembic\n")
        alembic_dir = tmp_path / "alembic"
        alembic_dir.mkdir()

        with patch("aegra_api.core.migrations.command") as mock_command:
            from aegra_api.core.migrations import run_migrations

            run_migrations()
            mock_command.upgrade.assert_called_once()
            args = mock_command.upgrade.call_args
            assert args[0][1] == "head"  # Second positional arg is "head"

    @pytest.mark.asyncio
    async def test_run_migrations_async_runs_in_thread(self):
        """Should run migrations via asyncio.to_thread."""
        with patch("aegra_api.core.migrations.asyncio.to_thread") as mock_to_thread:
            from aegra_api.core.migrations import run_migrations, run_migrations_async

            await run_migrations_async()
            mock_to_thread.assert_called_once_with(run_migrations)
