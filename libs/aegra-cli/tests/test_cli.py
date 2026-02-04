"""Tests for main CLI commands (version, dev, up, down)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aegra_cli.cli import cli

if TYPE_CHECKING:
    pass


def create_mock_popen(returncode: int = 0):
    """Create a mock Popen object that behaves like a completed process."""
    mock_process = MagicMock()
    mock_process.poll.return_value = returncode  # Process has finished
    mock_process.wait.return_value = returncode
    mock_process.returncode = returncode
    return mock_process


class TestVersion:
    """Tests for the version command."""

    def test_version_shows_aegra_cli_version(self, cli_runner: CliRunner) -> None:
        """Test that version command shows aegra-cli version."""
        result = cli_runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "aegra-cli" in result.output

    def test_version_shows_aegra_api_version(self, cli_runner: CliRunner) -> None:
        """Test that version command shows aegra-api version (or not installed)."""
        result = cli_runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "aegra-api" in result.output

    def test_version_flag(self, cli_runner: CliRunner) -> None:
        """Test that --version flag works on main CLI."""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "aegra-cli" in result.output


class TestDevCommand:
    """Tests for the dev command.

    Note: Most tests use --no-db-check to skip automatic PostgreSQL/Docker checks,
    allowing us to test the uvicorn command building in isolation.
    """

    def test_dev_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that dev command builds the correct uvicorn command."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(cli, ["dev", "--no-db-check"])

            # Verify subprocess.Popen was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]

            # Check command structure
            assert call_args[0] == sys.executable
            assert "-m" in call_args
            assert "uvicorn" in call_args
            assert "aegra_api.main:app" in call_args
            assert "--reload" in call_args

    def test_dev_default_host_and_port(self, cli_runner: CliRunner) -> None:
        """Test that dev command uses default host and port."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(cli, ["dev", "--no-db-check"])

            call_args = mock_popen.call_args[0][0]
            assert "--host" in call_args
            host_idx = call_args.index("--host")
            assert call_args[host_idx + 1] == "127.0.0.1"

            assert "--port" in call_args
            port_idx = call_args.index("--port")
            assert call_args[port_idx + 1] == "8000"

    def test_dev_custom_host(self, cli_runner: CliRunner) -> None:
        """Test that dev command accepts custom host."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(cli, ["dev", "--no-db-check", "--host", "0.0.0.0"])

            call_args = mock_popen.call_args[0][0]
            host_idx = call_args.index("--host")
            assert call_args[host_idx + 1] == "0.0.0.0"

    def test_dev_custom_port(self, cli_runner: CliRunner) -> None:
        """Test that dev command accepts custom port."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(cli, ["dev", "--no-db-check", "--port", "3000"])

            call_args = mock_popen.call_args[0][0]
            port_idx = call_args.index("--port")
            assert call_args[port_idx + 1] == "3000"

    def test_dev_custom_app(self, cli_runner: CliRunner) -> None:
        """Test that dev command accepts custom app path."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(cli, ["dev", "--no-db-check", "--app", "myapp.main:app"])

            call_args = mock_popen.call_args[0][0]
            assert "myapp.main:app" in call_args

    def test_dev_uvicorn_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when uvicorn is not installed."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("uvicorn not found")
            result = cli_runner.invoke(cli, ["dev", "--no-db-check"])

            assert result.exit_code == 1
            assert "uvicorn is not installed" in result.output

    def test_dev_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test handling of keyboard interrupt during dev server."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_process = create_mock_popen(0)
            mock_process.wait.side_effect = KeyboardInterrupt()
            mock_popen.return_value = mock_process
            result = cli_runner.invoke(cli, ["dev", "--no-db-check"])

            assert result.exit_code == 0
            assert "Server stopped by user" in result.output

    def test_dev_shows_server_info(self, cli_runner: CliRunner) -> None:
        """Test that dev command shows server info in output."""
        with patch("aegra_cli.cli.subprocess.Popen") as mock_popen:
            mock_popen.return_value = create_mock_popen(0)
            result = cli_runner.invoke(
                cli, ["dev", "--no-db-check", "--host", "0.0.0.0", "--port", "9000"]
            )

            assert "0.0.0.0" in result.output
            assert "9000" in result.output


class TestUpCommand:
    """Tests for the up command."""

    def test_up_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that up command builds the correct docker compose command."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]

            assert call_args[0] == "docker"
            assert call_args[1] == "compose"
            assert "up" in call_args
            assert "-d" in call_args

    def test_up_with_build_flag(self, cli_runner: CliRunner) -> None:
        """Test that up command includes --build when specified."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up", "--build"])

            call_args = mock_run.call_args[0][0]
            assert "--build" in call_args

    def test_up_with_specific_services(self, cli_runner: CliRunner) -> None:
        """Test that up command passes specific services."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up", "postgres", "redis"])

            call_args = mock_run.call_args[0][0]
            assert "postgres" in call_args
            assert "redis" in call_args

    def test_up_with_compose_file(self, cli_runner: CliRunner, mock_compose_file: Path) -> None:
        """Test that up command accepts custom compose file."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up", "-f", str(mock_compose_file)])

            call_args = mock_run.call_args[0][0]
            assert "-f" in call_args
            file_idx = call_args.index("-f")
            assert call_args[file_idx + 1] == str(mock_compose_file)

    def test_up_success_message(self, cli_runner: CliRunner) -> None:
        """Test that up command shows success message."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up"])

            assert "Services started successfully" in result.output

    def test_up_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that up command shows error on failure."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["up"])

            assert result.exit_code == 1
            assert "Error" in result.output

    def test_up_docker_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when docker is not installed."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("docker not found")
            result = cli_runner.invoke(cli, ["up"])

            assert result.exit_code == 1
            assert "docker is not installed" in result.output

    def test_up_shows_running_command(self, cli_runner: CliRunner) -> None:
        """Test that up command shows the command being run."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["up"])

            assert "Running:" in result.output
            assert "docker compose" in result.output


class TestDownCommand:
    """Tests for the down command."""

    def test_down_builds_correct_command(self, cli_runner: CliRunner) -> None:
        """Test that down command builds the correct docker compose command."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]

            assert call_args[0] == "docker"
            assert call_args[1] == "compose"
            assert "down" in call_args

    def test_down_with_volumes_flag(self, cli_runner: CliRunner) -> None:
        """Test that down command includes -v when --volumes is specified."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down", "--volumes"])

            call_args = mock_run.call_args[0][0]
            assert "-v" in call_args

    def test_down_with_v_short_flag(self, cli_runner: CliRunner) -> None:
        """Test that down command accepts -v short flag."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down", "-v"])

            call_args = mock_run.call_args[0][0]
            assert "-v" in call_args

    def test_down_volumes_shows_warning(self, cli_runner: CliRunner) -> None:
        """Test that down --volumes shows a warning about data loss."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down", "-v"])

            assert "Warning" in result.output
            assert "data will be lost" in result.output

    def test_down_with_specific_services(self, cli_runner: CliRunner) -> None:
        """Test that down command passes specific services."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down", "postgres"])

            call_args = mock_run.call_args[0][0]
            assert "postgres" in call_args

    def test_down_with_compose_file(self, cli_runner: CliRunner, mock_compose_file: Path) -> None:
        """Test that down command accepts custom compose file."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down", "-f", str(mock_compose_file)])

            call_args = mock_run.call_args[0][0]
            assert "-f" in call_args
            file_idx = call_args.index("-f")
            assert call_args[file_idx + 1] == str(mock_compose_file)

    def test_down_success_message(self, cli_runner: CliRunner) -> None:
        """Test that down command shows success message."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down"])

            assert "Services stopped successfully" in result.output

    def test_down_failure_shows_error(self, cli_runner: CliRunner) -> None:
        """Test that down command shows error on failure."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = cli_runner.invoke(cli, ["down"])

            assert result.exit_code == 1
            assert "Error" in result.output

    def test_down_docker_not_installed(self, cli_runner: CliRunner) -> None:
        """Test error handling when docker is not installed."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("docker not found")
            result = cli_runner.invoke(cli, ["down"])

            assert result.exit_code == 1
            assert "docker is not installed" in result.output

    def test_down_shows_running_command(self, cli_runner: CliRunner) -> None:
        """Test that down command shows the command being run."""
        with patch("aegra_cli.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = cli_runner.invoke(cli, ["down"])

            assert "Running:" in result.output
            assert "docker compose" in result.output


class TestCLIHelp:
    """Tests for CLI help messages."""

    def test_main_help(self, cli_runner: CliRunner) -> None:
        """Test that main CLI shows help."""
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Aegra CLI" in result.output

    def test_version_help(self, cli_runner: CliRunner) -> None:
        """Test that version command shows help."""
        result = cli_runner.invoke(cli, ["version", "--help"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

    def test_dev_help(self, cli_runner: CliRunner) -> None:
        """Test that dev command shows help."""
        result = cli_runner.invoke(cli, ["dev", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--app" in result.output

    def test_up_help(self, cli_runner: CliRunner) -> None:
        """Test that up command shows help."""
        result = cli_runner.invoke(cli, ["up", "--help"])
        assert result.exit_code == 0
        assert "--file" in result.output
        assert "--build" in result.output

    def test_down_help(self, cli_runner: CliRunner) -> None:
        """Test that down command shows help."""
        result = cli_runner.invoke(cli, ["down", "--help"])
        assert result.exit_code == 0
        assert "--file" in result.output
        assert "--volumes" in result.output


class TestCLIEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unknown_command(self, cli_runner: CliRunner) -> None:
        """Test that unknown commands show an error."""
        result = cli_runner.invoke(cli, ["unknown-command"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_dev_invalid_port(self, cli_runner: CliRunner) -> None:
        """Test that dev command rejects invalid port."""
        result = cli_runner.invoke(cli, ["dev", "--port", "not-a-number"])
        assert result.exit_code != 0

    def test_up_nonexistent_compose_file(self, cli_runner: CliRunner) -> None:
        """Test that up command handles nonexistent compose file."""
        result = cli_runner.invoke(cli, ["up", "-f", "/nonexistent/docker-compose.yml"])
        assert result.exit_code != 0

    def test_down_nonexistent_compose_file(self, cli_runner: CliRunner) -> None:
        """Test that down command handles nonexistent compose file."""
        result = cli_runner.invoke(cli, ["down", "-f", "/nonexistent/docker-compose.yml"])
        assert result.exit_code != 0
