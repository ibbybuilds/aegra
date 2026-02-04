"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from click.testing import CliRunner

from aegra_cli.cli import cli
from aegra_cli.commands.init import (
    AEGRA_CONFIG_TEMPLATE,
    DOCKER_COMPOSE_TEMPLATE,
    ENV_EXAMPLE_TEMPLATE,
    EXAMPLE_GRAPH_TEMPLATE,
)

if TYPE_CHECKING:
    pass


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_aegra_json(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates aegra.json file."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path("aegra.json").exists()

            content = json.loads(Path("aegra.json").read_text())
            assert content == AEGRA_CONFIG_TEMPLATE

    def test_init_creates_env_example(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates .env.example file."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path(".env.example").exists()

            content = Path(".env.example").read_text()
            assert "POSTGRES_USER" in content
            assert "POSTGRES_PASSWORD" in content
            assert "AUTH_TYPE" in content

    def test_init_creates_example_graph(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates example graph file."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path("graphs/example/graph.py").exists()

            content = Path("graphs/example/graph.py").read_text()
            assert "StateGraph" in content
            assert "graph = builder.compile()" in content

    def test_init_creates_init_files(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates __init__.py files for graph packages."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path("graphs/__init__.py").exists()
            assert Path("graphs/example/__init__.py").exists()

    def test_init_with_docker_flag(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates docker-compose.yml with --docker flag."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            assert result.exit_code == 0
            assert Path("docker-compose.yml").exists()

            content = Path("docker-compose.yml").read_text()
            assert "postgres" in content
            assert "aegra" in content

    def test_init_without_docker_flag(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init does not create docker-compose.yml without --docker flag."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert not Path("docker-compose.yml").exists()

    def test_init_skips_existing_files(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init skips existing files without --force."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create existing file
            Path("aegra.json").write_text('{"existing": "config"}')

            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert "SKIP" in result.output

            # Verify original content is preserved
            content = json.loads(Path("aegra.json").read_text())
            assert content == {"existing": "config"}

    def test_init_force_overwrites_files(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init --force overwrites existing files."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create existing file
            Path("aegra.json").write_text('{"existing": "config"}')

            result = cli_runner.invoke(cli, ["init", "--force"])

            assert result.exit_code == 0
            assert "CREATE" in result.output

            # Verify content is overwritten
            content = json.loads(Path("aegra.json").read_text())
            assert content == AEGRA_CONFIG_TEMPLATE

    def test_init_custom_path(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates files in custom directory with --path."""
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        result = cli_runner.invoke(cli, ["init", "--path", str(project_dir)])

        assert result.exit_code == 0
        assert (project_dir / "aegra.json").exists()
        assert (project_dir / ".env.example").exists()
        assert (project_dir / "graphs" / "example" / "graph.py").exists()

    def test_init_creates_parent_directories(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates necessary parent directories."""
        project_dir = tmp_path / "nested" / "project"

        result = cli_runner.invoke(cli, ["init", "--path", str(project_dir)])

        assert result.exit_code == 0
        assert (project_dir / "graphs" / "example" / "graph.py").exists()

    def test_init_shows_files_created_count(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init shows count of files created."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert "files created" in result.output

    def test_init_shows_next_steps(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init shows next steps after completion."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert "Next steps" in result.output
            assert ".env.example" in result.output
            assert "aegra.json" in result.output

    def test_init_shows_docker_instructions(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init shows Docker instructions when --docker is used."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            assert result.exit_code == 0
            assert "Docker" in result.output
            assert "docker-compose" in result.output


class TestInitFileContents:
    """Tests for the content of generated files."""

    def test_aegra_config_has_graphs_section(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that aegra.json has graphs configuration."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            content = json.loads(Path("aegra.json").read_text())
            assert "graphs" in content
            assert "agent" in content["graphs"]

    def test_env_example_has_required_vars(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that .env.example has all required environment variables."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            content = Path(".env.example").read_text()
            required_vars = [
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "POSTGRES_HOST",
                "POSTGRES_DB",
                "AUTH_TYPE",
            ]
            for var in required_vars:
                assert var in content

    def test_example_graph_is_valid_python(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that example graph is valid Python syntax."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            content = Path("graphs/example/graph.py").read_text()
            # This will raise SyntaxError if invalid
            compile(content, "graph.py", "exec")

    def test_example_graph_has_required_imports(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test that example graph has required imports."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            content = Path("graphs/example/graph.py").read_text()
            assert "from langgraph.graph import StateGraph" in content
            assert "TypedDict" in content

    def test_example_graph_exports_graph(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that example graph exports 'graph' variable."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            content = Path("graphs/example/graph.py").read_text()
            assert "graph = builder.compile()" in content

    def test_docker_compose_has_postgres(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that docker-compose.yml includes postgres service."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            content = Path("docker-compose.yml").read_text()
            assert "postgres:" in content
            assert "image: postgres" in content
            assert "5432:5432" in content

    def test_docker_compose_has_aegra_service(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that docker-compose.yml includes aegra service."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            content = Path("docker-compose.yml").read_text()
            assert "aegra:" in content
            assert "8000:8000" in content

    def test_docker_compose_has_volumes(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that docker-compose.yml includes volumes section."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            content = Path("docker-compose.yml").read_text()
            assert "volumes:" in content
            assert "postgres_data:" in content


class TestInitEdgeCases:
    """Tests for edge cases in init command."""

    def test_init_in_nonempty_directory(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init works in a non-empty directory."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create some unrelated files
            Path("README.md").write_text("# My Project")
            Path("src").mkdir()
            Path("src/main.py").write_text("print('hello')")

            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path("aegra.json").exists()
            # Ensure other files are preserved
            assert Path("README.md").exists()
            assert Path("src/main.py").exists()

    def test_init_multiple_times(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that running init multiple times without --force skips existing files."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # First init
            result1 = cli_runner.invoke(cli, ["init"])
            assert result1.exit_code == 0

            # Second init
            result2 = cli_runner.invoke(cli, ["init"])
            assert result2.exit_code == 0
            assert "SKIP" in result2.output
            assert "skipped" in result2.output

    def test_init_force_multiple_times(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that running init --force multiple times overwrites files."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # First init
            result1 = cli_runner.invoke(cli, ["init", "--force"])
            assert result1.exit_code == 0

            # Second init with force
            result2 = cli_runner.invoke(cli, ["init", "--force"])
            assert result2.exit_code == 0
            # All files should be created (overwritten)
            assert "files created" in result2.output

    def test_init_help(self, cli_runner: CliRunner) -> None:
        """Test that init --help shows all options."""
        result = cli_runner.invoke(cli, ["init", "--help"])

        assert result.exit_code == 0
        assert "--docker" in result.output
        assert "--force" in result.output
        assert "--path" in result.output


class TestInitTemplates:
    """Tests to verify template constants are correct."""

    def test_aegra_config_template_is_valid_dict(self) -> None:
        """Test that AEGRA_CONFIG_TEMPLATE is a valid dictionary."""
        assert isinstance(AEGRA_CONFIG_TEMPLATE, dict)
        assert "graphs" in AEGRA_CONFIG_TEMPLATE

    def test_env_example_template_has_content(self) -> None:
        """Test that ENV_EXAMPLE_TEMPLATE has content."""
        assert len(ENV_EXAMPLE_TEMPLATE) > 0
        assert "POSTGRES" in ENV_EXAMPLE_TEMPLATE

    def test_example_graph_template_is_valid_python(self) -> None:
        """Test that EXAMPLE_GRAPH_TEMPLATE is valid Python."""
        compile(EXAMPLE_GRAPH_TEMPLATE, "graph.py", "exec")

    def test_docker_compose_template_has_services(self) -> None:
        """Test that DOCKER_COMPOSE_TEMPLATE has services."""
        assert "services:" in DOCKER_COMPOSE_TEMPLATE
        assert "postgres:" in DOCKER_COMPOSE_TEMPLATE
        assert "aegra:" in DOCKER_COMPOSE_TEMPLATE
