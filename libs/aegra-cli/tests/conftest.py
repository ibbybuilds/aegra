"""Pytest fixtures for aegra-cli tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI test runner.

    Returns:
        A CliRunner instance for testing CLI commands.
    """
    return CliRunner()


@pytest.fixture
def isolated_cli_runner() -> CliRunner:
    """Create an isolated Click CLI test runner with a temporary filesystem.

    Returns:
        A CliRunner with mix_stderr=False for cleaner output testing.
    """
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_subprocess_run() -> Generator[MagicMock, None, None]:
    """Mock subprocess.run for testing commands that execute external processes.

    Yields:
        A MagicMock that replaces subprocess.run.
    """
    with patch("subprocess.run") as mock_run:
        # Default to successful execution
        mock_run.return_value.returncode = 0
        yield mock_run


@pytest.fixture
def mock_subprocess_run_failure() -> Generator[MagicMock, None, None]:
    """Mock subprocess.run that simulates a command failure.

    Yields:
        A MagicMock that replaces subprocess.run with a non-zero return code.
    """
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        yield mock_run


@pytest.fixture
def mock_subprocess_not_found() -> Generator[MagicMock, None, None]:
    """Mock subprocess.run that raises FileNotFoundError.

    Yields:
        A MagicMock that raises FileNotFoundError when called.
    """
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("Command not found")
        yield mock_run


@pytest.fixture
def mock_subprocess_keyboard_interrupt() -> Generator[MagicMock, None, None]:
    """Mock subprocess.run that raises KeyboardInterrupt.

    Yields:
        A MagicMock that raises KeyboardInterrupt when called.
    """
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()
        yield mock_run


@pytest.fixture
def mock_sys_executable() -> Generator[str, None, None]:
    """Provide a consistent value for sys.executable in tests.

    Yields:
        The path to the Python executable.
    """
    with patch.object(sys, "executable", "/usr/bin/python"):
        yield "/usr/bin/python"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory for testing.

    Args:
        tmp_path: pytest's built-in temporary path fixture.

    Returns:
        Path to the temporary project directory.
    """
    return tmp_path / "test_project"


@pytest.fixture
def existing_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with existing files.

    Args:
        tmp_path: pytest's built-in temporary path fixture.

    Returns:
        Path to the temporary project directory with existing files.
    """
    project_dir = tmp_path / "existing_project"
    project_dir.mkdir(parents=True)

    # Create some existing files
    (project_dir / "aegra.json").write_text('{"existing": "config"}')
    (project_dir / ".env.example").write_text("EXISTING=value")

    return project_dir


@pytest.fixture
def mock_compose_file(tmp_path: Path) -> Path:
    """Create a mock docker-compose file for testing.

    Args:
        tmp_path: pytest's built-in temporary path fixture.

    Returns:
        Path to the mock docker-compose.yml file.
    """
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """
version: "3.8"
services:
  postgres:
    image: pgvector/pgvector:pg18
"""
    )
    return compose_file
