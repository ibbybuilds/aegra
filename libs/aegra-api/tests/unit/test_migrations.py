"""Tests for aegra_api.core.migrations module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
    async def test_run_migrations_async_dispatches_to_lockfree_path(self):
        """run_migrations_async should hand off to the lock-free helper."""
        with patch("aegra_api.core.migrations.asyncio.to_thread") as mock_to_thread:
            from aegra_api.core.migrations import (
                run_migrations_async,
                run_migrations_if_needed,
            )

            await run_migrations_async()
            mock_to_thread.assert_called_once_with(run_migrations_if_needed)


class TestRunMigrationsIfNeeded:
    """Tests for the lock-free fast-path used at FastAPI startup."""

    def _setup_alembic_ini(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
        (tmp_path / "alembic").mkdir()

    def test_skips_upgrade_when_database_at_head(self, tmp_path, monkeypatch):
        """When current revision matches head, no upgrade is invoked."""
        self._setup_alembic_ini(tmp_path, monkeypatch)

        with (
            patch("aegra_api.core.migrations._is_database_up_to_date", return_value=True) as mock_check,
            patch("aegra_api.core.migrations.command") as mock_command,
        ):
            from aegra_api.core.migrations import run_migrations_if_needed

            run_migrations_if_needed()

            mock_check.assert_called_once()
            mock_command.upgrade.assert_not_called()

    def test_runs_upgrade_when_database_behind_head(self, tmp_path, monkeypatch):
        """When the precheck reports drift, upgrade is invoked."""
        self._setup_alembic_ini(tmp_path, monkeypatch)

        with (
            patch("aegra_api.core.migrations._is_database_up_to_date", return_value=False),
            patch("aegra_api.core.migrations.command") as mock_command,
        ):
            from aegra_api.core.migrations import run_migrations_if_needed

            run_migrations_if_needed()

            mock_command.upgrade.assert_called_once()
            assert mock_command.upgrade.call_args[0][1] == "head"

    def test_falls_back_to_upgrade_when_precheck_fails(self, tmp_path, monkeypatch):
        """If the precheck raises (e.g. alembic_version missing on first install)
        the upgrade still runs so a fresh database can bootstrap.
        """
        self._setup_alembic_ini(tmp_path, monkeypatch)

        with (
            patch(
                "aegra_api.core.migrations._is_database_up_to_date",
                side_effect=RuntimeError("alembic_version table missing"),
            ),
            patch("aegra_api.core.migrations.command") as mock_command,
        ):
            from aegra_api.core.migrations import run_migrations_if_needed

            run_migrations_if_needed()

            mock_command.upgrade.assert_called_once()


class TestIsDatabaseUpToDate:
    """Tests for the lock-free revision precheck helper."""

    def test_returns_true_when_revisions_match(self):
        from aegra_api.core.migrations import _is_database_up_to_date

        cfg = MagicMock()
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        ctx = MagicMock()
        ctx.get_current_revision.return_value = "abc123"
        script = MagicMock()
        script.get_current_head.return_value = "abc123"

        with (
            patch("aegra_api.core.migrations.create_engine", return_value=engine),
            patch("aegra_api.core.migrations.MigrationContext.configure", return_value=ctx),
            patch("aegra_api.core.migrations.ScriptDirectory.from_config", return_value=script),
        ):
            assert _is_database_up_to_date(cfg) is True

    def test_returns_false_when_revisions_differ(self):
        from aegra_api.core.migrations import _is_database_up_to_date

        cfg = MagicMock()
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        ctx = MagicMock()
        ctx.get_current_revision.return_value = "abc123"
        script = MagicMock()
        script.get_current_head.return_value = "def456"

        with (
            patch("aegra_api.core.migrations.create_engine", return_value=engine),
            patch("aegra_api.core.migrations.MigrationContext.configure", return_value=ctx),
            patch("aegra_api.core.migrations.ScriptDirectory.from_config", return_value=script),
        ):
            assert _is_database_up_to_date(cfg) is False

    def test_returns_false_when_no_current_revision(self):
        """A fresh database with no alembic_version row needs the upgrade path."""
        from aegra_api.core.migrations import _is_database_up_to_date

        cfg = MagicMock()
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        ctx = MagicMock()
        ctx.get_current_revision.return_value = None
        script = MagicMock()
        script.get_current_head.return_value = "abc123"

        with (
            patch("aegra_api.core.migrations.create_engine", return_value=engine),
            patch("aegra_api.core.migrations.MigrationContext.configure", return_value=ctx),
            patch("aegra_api.core.migrations.ScriptDirectory.from_config", return_value=script),
        ):
            assert _is_database_up_to_date(cfg) is False

    def test_returns_true_when_script_directory_empty(self):
        """No revisions at all means nothing to apply; skip the upgrade path."""
        from aegra_api.core.migrations import _is_database_up_to_date

        cfg = MagicMock()
        script = MagicMock()
        script.get_current_head.return_value = None

        with (
            patch("aegra_api.core.migrations.ScriptDirectory.from_config", return_value=script),
            patch("aegra_api.core.migrations.create_engine") as mock_create_engine,
        ):
            assert _is_database_up_to_date(cfg) is True
            # Should short-circuit before opening any DB connection.
            mock_create_engine.assert_not_called()

    def test_disposes_engine_on_success_and_failure(self):
        """The short-lived engine must be disposed even when revision lookup fails."""
        from aegra_api.core.migrations import _is_database_up_to_date

        cfg = MagicMock()
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        engine.connect.return_value.__exit__.return_value = False

        with (
            patch("aegra_api.core.migrations.create_engine", return_value=engine),
            patch(
                "aegra_api.core.migrations.MigrationContext.configure",
                side_effect=RuntimeError("boom"),
            ),
            patch("aegra_api.core.migrations.ScriptDirectory.from_config", return_value=MagicMock()),
            pytest.raises(RuntimeError),
        ):
            _is_database_up_to_date(cfg)
        engine.dispose.assert_called_once()
