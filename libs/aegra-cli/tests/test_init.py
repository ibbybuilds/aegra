"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from click.testing import CliRunner

from aegra_cli.cli import cli
from aegra_cli.commands.init import (
    get_aegra_config,
    get_docker_compose_dev,
    get_docker_compose_prod,
    get_dockerfile,
    get_env_example,
    get_example_graph,
    slugify,
)

if TYPE_CHECKING:
    pass


class TestSlugify:
    """Tests for the slugify function."""

    def test_slugify_simple_name(self) -> None:
        """Test slugify with simple name."""
        assert slugify("myproject") == "myproject"

    def test_slugify_with_spaces(self) -> None:
        """Test slugify converts spaces to underscores."""
        assert slugify("My Project") == "my_project"

    def test_slugify_with_hyphens(self) -> None:
        """Test slugify converts hyphens to underscores."""
        assert slugify("my-project") == "my_project"

    def test_slugify_with_special_chars(self) -> None:
        """Test slugify removes special characters."""
        assert slugify("My App 2.0!") == "my_app_20"

    def test_slugify_with_leading_number(self) -> None:
        """Test slugify handles leading numbers."""
        assert slugify("123project") == "project_123project"

    def test_slugify_empty_string(self) -> None:
        """Test slugify handles empty string."""
        assert slugify("") == "aegra_project"

    def test_slugify_only_special_chars(self) -> None:
        """Test slugify handles string with only special chars."""
        assert slugify("!@#$%") == "aegra_project"


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_aegra_json(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates aegra.json file."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert Path("aegra.json").exists()

            content = json.loads(Path("aegra.json").read_text())
            assert "graphs" in content
            assert "name" in content

    def test_init_with_custom_name(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init uses custom project name."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--name", "My Awesome Agent"])

            assert result.exit_code == 0
            content = json.loads(Path("aegra.json").read_text())
            assert content["name"] == "My Awesome Agent"
            assert "my_awesome_agent" in content["graphs"]

    def test_init_with_short_name_flag(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init accepts -n short flag for name."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "test-agent"])

            assert result.exit_code == 0
            content = json.loads(Path("aegra.json").read_text())
            assert content["name"] == "test-agent"

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
        """Test that init creates example graph file with project name."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "my_agent"])

            assert result.exit_code == 0
            # Graph should be in directory matching slugified name
            assert Path("graphs/my_agent/graph.py").exists()

            content = Path("graphs/my_agent/graph.py").read_text()
            assert "StateGraph" in content
            assert "graph = builder.compile()" in content

    def test_init_creates_init_files(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates __init__.py files for graph packages."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "test"])

            assert result.exit_code == 0
            assert Path("graphs/__init__.py").exists()
            assert Path("graphs/test/__init__.py").exists()

    def test_init_with_docker_flag(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates Docker files with --docker flag."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker", "-n", "myapp"])

            assert result.exit_code == 0
            # Dev compose file
            assert Path("docker-compose.yml").exists()
            content = Path("docker-compose.yml").read_text()
            assert "postgres" in content
            assert "myapp-postgres" in content

            # Prod compose file
            assert Path("docker-compose.prod.yml").exists()
            prod_content = Path("docker-compose.prod.yml").read_text()
            assert "postgres" in prod_content
            assert "myapp:" in prod_content  # Service name uses slug

            # Dockerfile
            assert Path("Dockerfile").exists()
            dockerfile_content = Path("Dockerfile").read_text()
            assert "aegra" in dockerfile_content

    def test_init_without_docker_flag(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init does not create Docker files without --docker flag."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert not Path("docker-compose.yml").exists()
            assert not Path("docker-compose.prod.yml").exists()
            assert not Path("Dockerfile").exists()

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
            assert "graphs" in content

    def test_init_custom_path(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates files in custom directory with --path."""
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        result = cli_runner.invoke(cli, ["init", "--path", str(project_dir)])

        assert result.exit_code == 0
        assert (project_dir / "aegra.json").exists()
        assert (project_dir / ".env.example").exists()

    def test_init_creates_parent_directories(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that init creates necessary parent directories."""
        project_dir = tmp_path / "nested" / "project"

        result = cli_runner.invoke(cli, ["init", "--path", str(project_dir), "-n", "test"])

        assert result.exit_code == 0
        assert (project_dir / "graphs" / "test" / "graph.py").exists()

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


class TestInitFileContents:
    """Tests for the content of generated files."""

    def test_aegra_config_has_graphs_section(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that aegra.json has graphs configuration."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "test_agent"])

            content = json.loads(Path("aegra.json").read_text())
            assert "graphs" in content
            assert "test_agent" in content["graphs"]

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
            result = cli_runner.invoke(cli, ["init", "-n", "test"])

            content = Path("graphs/test/graph.py").read_text()
            # This will raise SyntaxError if invalid
            compile(content, "graph.py", "exec")

    def test_example_graph_has_required_imports(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test that example graph has required imports."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "test"])

            content = Path("graphs/test/graph.py").read_text()
            assert "from langgraph.graph import" in content
            assert "StateGraph" in content
            assert "TypedDict" in content

    def test_example_graph_exports_graph(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that example graph exports 'graph' variable."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "-n", "test"])

            content = Path("graphs/test/graph.py").read_text()
            assert "graph = builder.compile()" in content

    def test_docker_compose_dev_has_postgres(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that docker-compose.yml (dev) includes postgres service only."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            content = Path("docker-compose.yml").read_text()
            assert "postgres:" in content
            assert "image: pgvector/pgvector:pg18" in content
            assert "POSTGRES_PORT" in content  # Uses env var for port
            # Dev compose should NOT have the app service
            assert "build:" not in content

    def test_docker_compose_prod_has_project_service(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test that docker-compose.prod.yml includes project service."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker", "-n", "myapp"])

            content = Path("docker-compose.prod.yml").read_text()
            assert "myapp:" in content
            assert "PORT" in content  # Uses env var for port
            assert "build:" in content  # Prod has build context

    def test_docker_compose_has_volumes(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that docker-compose files include volumes section."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            # Check dev compose
            dev_content = Path("docker-compose.yml").read_text()
            assert "volumes:" in dev_content
            assert "postgres_data:" in dev_content

            # Check prod compose
            prod_content = Path("docker-compose.prod.yml").read_text()
            assert "volumes:" in prod_content
            assert "postgres_data:" in prod_content

    def test_dockerfile_content(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Test that Dockerfile has proper content."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", "--docker"])

            content = Path("Dockerfile").read_text()
            assert "FROM python" in content
            assert "pip install" in content
            assert "aegra" in content
            assert "EXPOSE 8000" in content


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
        assert "--name" in result.output
        assert "-n" in result.output
        assert "--docker" in result.output
        assert "--force" in result.output
        assert "--path" in result.output


class TestInitTemplates:
    """Tests to verify template functions are correct."""

    def test_get_aegra_config_returns_valid_dict(self) -> None:
        """Test that get_aegra_config returns a valid dictionary."""
        config = get_aegra_config("My Project", "my_project")
        assert isinstance(config, dict)
        assert "name" in config
        assert config["name"] == "My Project"
        assert "graphs" in config
        assert "my_project" in config["graphs"]

    def test_get_env_example_has_content(self) -> None:
        """Test that get_env_example has content."""
        env = get_env_example("myapp")
        assert len(env) > 0
        assert "POSTGRES" in env
        assert "myapp" in env

    def test_get_example_graph_is_valid_python(self) -> None:
        """Test that get_example_graph produces valid Python."""
        graph = get_example_graph("My Project")
        compile(graph, "graph.py", "exec")

    def test_get_docker_compose_dev_has_postgres_only(self) -> None:
        """Test that get_docker_compose_dev has postgres only."""
        compose = get_docker_compose_dev("myapp")
        assert "services:" in compose
        assert "postgres:" in compose
        assert "myapp-postgres" in compose  # container_name
        # Should NOT have app service
        assert "build:" not in compose

    def test_get_docker_compose_prod_has_all_services(self) -> None:
        """Test that get_docker_compose_prod has all services."""
        compose = get_docker_compose_prod("myapp")
        assert "services:" in compose
        assert "postgres:" in compose
        assert "myapp:" in compose  # app service
        assert "myapp-postgres" in compose  # postgres container_name
        assert "myapp-api" in compose  # app container_name
        assert "build:" in compose  # has build context

    def test_get_dockerfile_has_aegra(self) -> None:
        """Test that get_dockerfile installs aegra."""
        dockerfile = get_dockerfile()
        assert "FROM python" in dockerfile
        assert "pip install" in dockerfile
        assert "aegra" in dockerfile
        assert '"aegra"' in dockerfile  # CMD uses JSON array format
