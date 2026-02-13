"""Tests for database migration commands."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aegra_cli.cli import cli

if TYPE_CHECKING:
    pass

# Patch targets — db.py imports these at the top level
_PATCH_GET_CONFIG = "aegra_cli.commands.db.get_alembic_config"
_PATCH_COMMAND = "aegra_cli.commands.db.command"


def _mock_config() -> MagicMock:
    """Create a mock alembic Config object."""
    cfg = MagicMock()
    cfg.print_stdout = None
    return cfg


class TestDbUpgradeCommand:
    """Tests for the db upgrade command."""

    def test_calls_alembic_upgrade_with_head(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade calls command.upgrade(cfg, 'head')."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            mock_cmd.upgrade.assert_called_once_with(mock_cfg, "head")
            assert result.exit_code == 0

    def test_shows_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade shows success message."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND),
        ):
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert "Database upgraded successfully" in result.output

    def test_shows_error_on_exception(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade shows error on alembic failure."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.upgrade.side_effect = RuntimeError("connection refused")
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic upgrade failed" in result.output

    def test_handles_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during upgrade."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.upgrade.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbDowngradeCommand:
    """Tests for the db downgrade command."""

    def test_default_revision_is_minus_one(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade uses -1 as default revision."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            mock_cmd.downgrade.assert_called_once_with(mock_cfg, "-1")
            assert result.exit_code == 0

    def test_custom_revision(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade accepts custom revision."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "downgrade", "--", "-2"])

            mock_cmd.downgrade.assert_called_once_with(mock_cfg, "-2")

    def test_specific_revision_hash(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade accepts specific revision hash."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "downgrade", "abc123"])

            mock_cmd.downgrade.assert_called_once_with(mock_cfg, "abc123")

    def test_base_revision_shows_warning(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade to base shows warning."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND),
        ):
            result = cli_runner.invoke(cli, ["db", "downgrade", "base"])

            assert "Warning" in result.output
            assert "base" in result.output

    def test_shows_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade shows success message."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND),
        ):
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert "Database downgraded successfully" in result.output

    def test_shows_error_on_exception(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade shows error on alembic failure."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.downgrade.side_effect = RuntimeError("migration failed")
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic downgrade failed" in result.output

    def test_handles_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during downgrade."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.downgrade.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbCurrentCommand:
    """Tests for the db current command."""

    def test_calls_alembic_current(self, cli_runner: CliRunner) -> None:
        """Test that db current calls command.current(cfg)."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "current"])

            mock_cmd.current.assert_called_once_with(mock_cfg)
            assert result.exit_code == 0

    def test_shows_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db current shows success message."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND),
        ):
            result = cli_runner.invoke(cli, ["db", "current"])

            assert "Current revision displayed above" in result.output

    def test_shows_error_on_exception(self, cli_runner: CliRunner) -> None:
        """Test that db current shows error on alembic failure."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.current.side_effect = RuntimeError("no database")
            result = cli_runner.invoke(cli, ["db", "current"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic current failed" in result.output

    def test_handles_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during current check."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.current.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "current"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbHistoryCommand:
    """Tests for the db history command."""

    def test_calls_alembic_history(self, cli_runner: CliRunner) -> None:
        """Test that db history calls command.history(cfg)."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "history"])

            mock_cmd.history.assert_called_once_with(mock_cfg, verbose=False)
            assert result.exit_code == 0

    def test_passes_verbose_flag(self, cli_runner: CliRunner) -> None:
        """Test that db history --verbose passes verbose=True."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "history", "--verbose"])

            mock_cmd.history.assert_called_once_with(mock_cfg, verbose=True)

    def test_verbose_short_flag(self, cli_runner: CliRunner) -> None:
        """Test that db history -v passes verbose=True."""
        mock_cfg = _mock_config()
        with (
            patch(_PATCH_GET_CONFIG, return_value=mock_cfg),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            result = cli_runner.invoke(cli, ["db", "history", "-v"])

            mock_cmd.history.assert_called_once_with(mock_cfg, verbose=True)

    def test_shows_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db history shows success message."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND),
        ):
            result = cli_runner.invoke(cli, ["db", "history"])

            assert "Migration history displayed above" in result.output

    def test_shows_error_on_exception(self, cli_runner: CliRunner) -> None:
        """Test that db history shows error on alembic failure."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.history.side_effect = RuntimeError("no migrations")
            result = cli_runner.invoke(cli, ["db", "history"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic history failed" in result.output

    def test_handles_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during history check."""
        with (
            patch(_PATCH_GET_CONFIG, return_value=_mock_config()),
            patch(_PATCH_COMMAND) as mock_cmd,
        ):
            mock_cmd.history.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "history"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbGroupHelp:
    """Tests for db command group help."""

    def test_db_help(self, cli_runner: CliRunner) -> None:
        """Test that db --help shows all subcommands."""
        result = cli_runner.invoke(cli, ["db", "--help"])

        assert result.exit_code == 0
        assert "upgrade" in result.output
        assert "downgrade" in result.output
        assert "current" in result.output
        assert "history" in result.output

    def test_db_upgrade_help(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade --help shows command details."""
        result = cli_runner.invoke(cli, ["db", "upgrade", "--help"])

        assert result.exit_code == 0
        assert "upgrade" in result.output.lower()
        assert "head" in result.output.lower()

    def test_db_downgrade_help(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade --help shows command details."""
        result = cli_runner.invoke(cli, ["db", "downgrade", "--help"])

        assert result.exit_code == 0
        assert "REVISION" in result.output
        assert "-1" in result.output

    def test_db_current_help(self, cli_runner: CliRunner) -> None:
        """Test that db current --help shows command details."""
        result = cli_runner.invoke(cli, ["db", "current", "--help"])

        assert result.exit_code == 0
        assert "current" in result.output.lower()

    def test_db_history_help(self, cli_runner: CliRunner) -> None:
        """Test that db history --help shows command details."""
        result = cli_runner.invoke(cli, ["db", "history", "--help"])

        assert result.exit_code == 0
        assert "--verbose" in result.output


class TestDbCommandIntegration:
    """Integration tests for db commands."""

    def test_db_is_registered_on_main_cli(self, cli_runner: CliRunner) -> None:
        """Test that db command group is registered on main CLI."""
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "db" in result.output

    def test_db_unknown_subcommand(self, cli_runner: CliRunner) -> None:
        """Test that unknown db subcommands show an error."""
        result = cli_runner.invoke(cli, ["db", "unknown-command"])

        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_all_commands_use_get_alembic_config(self, cli_runner: CliRunner) -> None:
        """Test that all db commands use get_alembic_config for path resolution."""
        commands = ["upgrade", "downgrade", "current", "history"]

        for cmd_name in commands:
            with (
                patch(_PATCH_GET_CONFIG, return_value=_mock_config()) as mock_get_cfg,
                patch(_PATCH_COMMAND),
            ):
                cli_runner.invoke(cli, ["db", cmd_name])

                assert mock_get_cfg.called, f"db {cmd_name} should call get_alembic_config()"
                mock_get_cfg.assert_called_once()
