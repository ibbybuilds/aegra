"""Tests for database migration commands."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

from click.testing import CliRunner

from aegra_cli.cli import cli

if TYPE_CHECKING:
    pass


class TestDbUpgradeCommand:
    """Tests for the db upgrade command."""

    def test_db_upgrade_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade builds the correct alembic command."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]

            assert call_args[0] == sys.executable
            assert "-m" in call_args
            assert "alembic" in call_args
            assert "upgrade" in call_args
            assert "head" in call_args

    def test_db_upgrade_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade shows success message."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert "Database upgraded successfully" in result.output

    def test_db_upgrade_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade shows error on failure."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic upgrade failed" in result.output

    def test_db_upgrade_alembic_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when alembic is not installed."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("alembic not found")
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert result.exit_code == 1
            assert "Alembic is not installed" in result.output

    def test_db_upgrade_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during upgrade."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output

    def test_db_upgrade_shows_running_command(self, cli_runner: CliRunner) -> None:
        """Test that db upgrade shows the command being run."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "upgrade"])

            assert "Running:" in result.output
            assert "alembic" in result.output
            assert "upgrade" in result.output


class TestDbDowngradeCommand:
    """Tests for the db downgrade command."""

    def test_db_downgrade_default_revision(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade uses -1 as default revision."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            call_args = mock_run.call_args[0][0]
            assert "downgrade" in call_args
            assert "-1" in call_args

    def test_db_downgrade_custom_revision(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade accepts custom revision."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            # Use -- to separate options from arguments to handle negative numbers
            result = cli_runner.invoke(cli, ["db", "downgrade", "--", "-2"])

            call_args = mock_run.call_args[0][0]
            assert "-2" in call_args

    def test_db_downgrade_specific_revision(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade accepts specific revision hash."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "downgrade", "abc123"])

            call_args = mock_run.call_args[0][0]
            assert "abc123" in call_args

    def test_db_downgrade_to_base(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade to base shows warning."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "downgrade", "base"])

            assert "Warning" in result.output
            assert "base" in result.output
            call_args = mock_run.call_args[0][0]
            assert "base" in call_args

    def test_db_downgrade_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade shows success message."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert "Database downgraded successfully" in result.output

    def test_db_downgrade_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that db downgrade shows error on failure."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic downgrade failed" in result.output

    def test_db_downgrade_alembic_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when alembic is not installed."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("alembic not found")
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert result.exit_code == 1
            assert "Alembic is not installed" in result.output

    def test_db_downgrade_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during downgrade."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "downgrade"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbCurrentCommand:
    """Tests for the db current command."""

    def test_db_current_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that db current builds the correct alembic command."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "current"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]

            assert call_args[0] == sys.executable
            assert "-m" in call_args
            assert "alembic" in call_args
            assert "current" in call_args

    def test_db_current_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db current shows success message."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "current"])

            assert "Current revision displayed above" in result.output

    def test_db_current_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that db current shows error on failure."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["db", "current"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic current failed" in result.output

    def test_db_current_alembic_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when alembic is not installed."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("alembic not found")
            result = cli_runner.invoke(cli, ["db", "current"])

            assert result.exit_code == 1
            assert "Alembic is not installed" in result.output

    def test_db_current_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during current check."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = cli_runner.invoke(cli, ["db", "current"])

            assert result.exit_code == 1
            assert "Operation cancelled by user" in result.output


class TestDbHistoryCommand:
    """Tests for the db history command."""

    def test_db_history_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that db history builds the correct alembic command."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "history"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]

            assert call_args[0] == sys.executable
            assert "-m" in call_args
            assert "alembic" in call_args
            assert "history" in call_args

    def test_db_history_without_verbose(self, cli_runner: CliRunner) -> None:
        """Test that db history without verbose does not include --verbose."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "history"])

            call_args = mock_run.call_args[0][0]
            assert "--verbose" not in call_args

    def test_db_history_with_verbose(self, cli_runner: CliRunner) -> None:
        """Test that db history --verbose includes the flag."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "history", "--verbose"])

            call_args = mock_run.call_args[0][0]
            assert "--verbose" in call_args

    def test_db_history_with_v_short_flag(self, cli_runner: CliRunner) -> None:
        """Test that db history -v includes the verbose flag."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "history", "-v"])

            call_args = mock_run.call_args[0][0]
            assert "--verbose" in call_args

    def test_db_history_success_message(self, cli_runner: CliRunner) -> None:
        """Test that db history shows success message."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["db", "history"])

            assert "Migration history displayed above" in result.output

    def test_db_history_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that db history shows error on failure."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["db", "history"])

            assert result.exit_code == 1
            assert "Error" in result.output
            assert "Alembic history failed" in result.output

    def test_db_history_alembic_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when alembic is not installed."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("alembic not found")
            result = cli_runner.invoke(cli, ["db", "history"])

            assert result.exit_code == 1
            assert "Alembic is not installed" in result.output

    def test_db_history_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during history check."""
        with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
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

    def test_db_commands_use_correct_python(self, cli_runner: CliRunner) -> None:
        """Test that db commands use sys.executable for Python interpreter."""
        commands = ["upgrade", "downgrade", "current", "history"]

        for command in commands:
            with patch("aegra_cli.commands.db.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                result = cli_runner.invoke(cli, ["db", command])

                call_args = mock_run.call_args[0][0]
                # Should use sys.executable, not hardcoded "python"
                assert call_args[0] == sys.executable
