"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from click.testing import CliRunner

from aegra_cli.cli import cli
from aegra_cli.templates import (
    get_docker_compose_dev,
    get_docker_compose_prod,
    get_dockerfile,
    get_template_choices,
    load_shared_file,
    load_template_manifest,
    render_env_example,
    render_template_file,
    slugify,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for the slugify function."""

    def test_simple_name(self: TestSlugify) -> None:
        assert slugify("myproject") == "myproject"

    def test_with_spaces(self: TestSlugify) -> None:
        assert slugify("My Project") == "my_project"

    def test_with_hyphens(self: TestSlugify) -> None:
        assert slugify("my-project") == "my_project"

    def test_with_special_chars(self: TestSlugify) -> None:
        assert slugify("My App 2.0!") == "my_app_20"

    def test_with_leading_number(self: TestSlugify) -> None:
        assert slugify("123project") == "project_123project"

    def test_empty_string(self: TestSlugify) -> None:
        assert slugify("") == "aegra_project"

    def test_only_special_chars(self: TestSlugify) -> None:
        assert slugify("!@#$%") == "aegra_project"


# ---------------------------------------------------------------------------
# Template registry & renderers
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    """Tests for template registry helpers."""

    def test_get_template_choices_returns_list(self: TestTemplateRegistry) -> None:
        choices = get_template_choices()
        assert isinstance(choices, list)
        assert len(choices) >= 2

    def test_each_template_has_required_keys(self: TestTemplateRegistry) -> None:
        for t in get_template_choices():
            assert "id" in t
            assert "name" in t
            assert "description" in t

    def test_load_manifest_simple_chatbot(self: TestTemplateRegistry) -> None:
        manifest = load_template_manifest("simple-chatbot")
        assert "files" in manifest
        assert "graph.py.template" in manifest["files"]

    def test_load_manifest_react_agent(self: TestTemplateRegistry) -> None:
        manifest = load_template_manifest("react-agent")
        assert "files" in manifest
        assert "tools.py.template" in manifest["files"]

    def test_render_template_file_substitutes_variables(self: TestTemplateRegistry) -> None:
        content = render_template_file(
            "simple-chatbot",
            "graph.py.template",
            {"project_name": "My Bot", "slug": "my_bot"},
        )
        assert "My Bot" in content
        assert "$project_name" not in content

    def test_render_env_example_substitutes_slug(self: TestTemplateRegistry) -> None:
        content = render_env_example({"slug": "test_app"})
        assert "test_app" in content
        assert "POSTGRES_USER" in content

    def test_load_shared_gitignore(self: TestTemplateRegistry) -> None:
        content = load_shared_file("gitignore")
        assert "__pycache__" in content
        assert ".env" in content


# ---------------------------------------------------------------------------
# Docker generators
# ---------------------------------------------------------------------------


class TestDockerGenerators:
    """Tests for Docker file generators."""

    def test_docker_compose_dev_postgres_only(self: TestDockerGenerators) -> None:
        compose = get_docker_compose_dev("myapp")
        assert "postgres:" in compose
        assert "myapp-postgres" in compose
        assert "build:" not in compose

    def test_docker_compose_prod_has_all_services(self: TestDockerGenerators) -> None:
        compose = get_docker_compose_prod("myapp")
        assert "postgres:" in compose
        assert "myapp:" in compose
        assert "myapp-api" in compose
        assert "build:" in compose

    def test_docker_compose_prod_mounts_src(self: TestDockerGenerators) -> None:
        compose = get_docker_compose_prod("myapp")
        assert "./src:/app/src:ro" in compose

    def test_dockerfile_installs_project(self: TestDockerGenerators) -> None:
        dockerfile = get_dockerfile()
        assert "FROM python" in dockerfile
        assert "pip install" in dockerfile
        assert "COPY pyproject.toml" in dockerfile
        assert "COPY src/" in dockerfile
        assert "EXPOSE 8000" in dockerfile


# ---------------------------------------------------------------------------
# init command — interactive (CliRunner input=)
# ---------------------------------------------------------------------------


class TestInitInteractive:
    """Tests for interactive init prompts."""

    def test_interactive_default_path_template_1(
        self: TestInitInteractive, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Interactive flow: default path, pick template 1."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            with patch("aegra_cli.commands.init._is_interactive", return_value=True):
                result = cli_runner.invoke(cli, ["init"], input=".\n1\n")
            assert result.exit_code == 0
            assert Path("aegra.json").exists()
            assert Path("pyproject.toml").exists()

    def test_interactive_custom_path(
        self: TestInitInteractive, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Interactive flow: enter a custom directory."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            with patch("aegra_cli.commands.init._is_interactive", return_value=True):
                result = cli_runner.invoke(cli, ["init"], input="./my-agent\n1\n")
            assert result.exit_code == 0
            assert Path("my-agent/aegra.json").exists()
            assert Path("my-agent/pyproject.toml").exists()

    def test_interactive_template_2(
        self: TestInitInteractive, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Interactive flow: pick template 2 (ReAct agent)."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            with patch("aegra_cli.commands.init._is_interactive", return_value=True):
                result = cli_runner.invoke(cli, ["init"], input=".\n2\n")
            assert result.exit_code == 0
            # ReAct agent should have tools.py
            slug = slugify(Path.cwd().name)
            assert Path(f"src/{slug}/tools.py").exists()


# ---------------------------------------------------------------------------
# init command — CLI flags (non-interactive)
# ---------------------------------------------------------------------------


class TestInitCLIFlags:
    """Tests for non-interactive CLI flag usage."""

    def test_path_argument_and_template_flag(
        self: TestInitCLIFlags, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """aegra init ./my-agent -t 1"""
        project_dir = tmp_path / "my-agent"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert (project_dir / "aegra.json").exists()
        assert (project_dir / "pyproject.toml").exists()
        assert (project_dir / ".env.example").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "README.md").exists()
        assert (project_dir / "docker-compose.yml").exists()
        assert (project_dir / "docker-compose.prod.yml").exists()
        assert (project_dir / "Dockerfile").exists()

    def test_path_with_name_flag(
        self: TestInitCLIFlags, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """aegra init ./my-agent -t 1 -n 'My Agent'"""
        project_dir = tmp_path / "my-agent"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "-n", "My Agent"])
        assert result.exit_code == 0

        config = json.loads((project_dir / "aegra.json").read_text())
        assert config["name"] == "My Agent"
        assert "my_agent" in config["graphs"]

    def test_react_template_creates_tools(
        self: TestInitCLIFlags, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """aegra init -t 2 creates tools.py for ReAct agent."""
        project_dir = tmp_path / "react-test"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "2"])
        assert result.exit_code == 0

        slug = slugify("react-test")
        assert (project_dir / f"src/{slug}/tools.py").exists()
        assert (project_dir / f"src/{slug}/graph.py").exists()

        # tools.py should contain tool definitions
        tools_content = (project_dir / f"src/{slug}/tools.py").read_text()
        assert "TOOLS" in tools_content
        assert "@tool" in tools_content

    def test_name_from_path(self: TestInitCLIFlags, cli_runner: CliRunner, tmp_path: Path) -> None:
        """When no --name, project name derives from directory."""
        project_dir = tmp_path / "my-cool-agent"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        config = json.loads((project_dir / "aegra.json").read_text())
        assert config["name"] == "my-cool-agent"

    def test_invalid_template_number(
        self: TestInitCLIFlags, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """Invalid template number shows error."""
        project_dir = tmp_path / "bad-template"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "99"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# File content validation
# ---------------------------------------------------------------------------


class TestInitFileContents:
    """Tests for the content of generated files."""

    def test_aegra_json_has_dependencies(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-deps"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        config = json.loads((project_dir / "aegra.json").read_text())
        assert "dependencies" in config
        assert "./src" in config["dependencies"]

    def test_aegra_json_graph_path_uses_src(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-graph"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        config = json.loads((project_dir / "aegra.json").read_text())
        slug = slugify("test-graph")
        assert config["graphs"][slug] == f"./src/{slug}/graph.py:graph"

    def test_pyproject_toml_has_aegra_dep(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-pyproject"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / "pyproject.toml").read_text()
        assert "aegra-cli" in content
        assert "langgraph" in content
        assert "langchain-openai" in content

    def test_graph_has_langgraph_imports(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-graph-imports"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        slug = slugify("test-graph-imports")
        content = (project_dir / f"src/{slug}/graph.py").read_text()
        assert "from langgraph.graph import" in content
        assert "StateGraph" in content
        assert "ChatOpenAI" in content

    def test_graph_exports_graph_variable(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-graph-var"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        slug = slugify("test-graph-var")
        content = (project_dir / f"src/{slug}/graph.py").read_text()
        assert "graph:" in content and "=" in content

    def test_env_example_has_required_vars(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-env"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / ".env.example").read_text()
        for var in ["POSTGRES_USER", "POSTGRES_PASSWORD", "AUTH_TYPE", "OPENAI_API_KEY"]:
            assert var in content

    def test_env_example_uses_slug(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "slug-test"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "-n", "My App"])
        assert result.exit_code == 0

        content = (project_dir / ".env.example").read_text()
        assert "my_app" in content

    def test_gitignore_has_standard_entries(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-gitignore"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / ".gitignore").read_text()
        assert "__pycache__" in content
        assert ".env" in content
        assert ".venv" in content

    def test_readme_has_project_name(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-readme"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "-n", "Cool Agent"])
        assert result.exit_code == 0

        content = (project_dir / "README.md").read_text()
        assert "Cool Agent" in content

    def test_docker_compose_dev_has_postgres(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-compose"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / "docker-compose.yml").read_text()
        assert "postgres:" in content
        assert "build:" not in content

    def test_docker_compose_prod_mounts_src(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-prod"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / "docker-compose.prod.yml").read_text()
        assert "./src:/app/src:ro" in content
        assert "build:" in content

    def test_dockerfile_installs_from_pyproject(
        self: TestInitFileContents, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-docker"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0

        content = (project_dir / "Dockerfile").read_text()
        assert "COPY pyproject.toml" in content
        assert "COPY src/" in content
        assert "pip install" in content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestInitEdgeCases:
    """Tests for edge cases in init command."""

    def test_force_overwrites_existing_files(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "force-test"
        project_dir.mkdir()
        (project_dir / "aegra.json").write_text('{"old": true}')

        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "--force"])
        assert result.exit_code == 0

        config = json.loads((project_dir / "aegra.json").read_text())
        assert "graphs" in config
        assert "old" not in config

    def test_skips_existing_files_without_force(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "skip-test"
        project_dir.mkdir()
        (project_dir / "aegra.json").write_text('{"old": true}')

        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert "SKIP" in result.output

        config = json.loads((project_dir / "aegra.json").read_text())
        assert config == {"old": True}

    def test_creates_nested_directories(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "deep" / "nested" / "project"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert (project_dir / "aegra.json").exists()

    def test_init_in_nonempty_directory(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "nonempty"
        project_dir.mkdir()
        (project_dir / "existing.txt").write_text("keep me")

        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert (project_dir / "existing.txt").read_text() == "keep me"
        assert (project_dir / "aegra.json").exists()

    def test_double_init_without_force_skips(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "double"
        cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert "SKIP" in result.output

    def test_double_init_with_force_overwrites(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "double-force"
        cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "--force"])
        assert result.exit_code == 0
        assert "CREATE" in result.output

    def test_shows_next_steps(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "steps-test"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1"])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "aegra dev" in result.output
        assert "pip install" in result.output

    def test_help_shows_options(self: TestInitEdgeCases, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "--template" in result.output
        assert "-t" in result.output
        assert "--name" in result.output
        assert "-n" in result.output
        assert "--force" in result.output

    def test_react_graph_imports_from_slug(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """ReAct graph.py should import tools from the correct package."""
        project_dir = tmp_path / "react-import"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "2"])
        assert result.exit_code == 0

        slug = slugify("react-import")
        content = (project_dir / f"src/{slug}/graph.py").read_text()
        assert f"from {slug}.tools import TOOLS" in content

    def test_init_current_dir_with_template_flag(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """aegra init . -t 1 should work without interactive prompts."""
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["init", ".", "-t", "1"])
            assert result.exit_code == 0
            assert Path("aegra.json").exists()

    def test_project_name_substituted_in_graph(
        self: TestInitEdgeCases, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "name-sub"
        result = cli_runner.invoke(cli, ["init", str(project_dir), "-t", "1", "-n", "Super Bot"])
        assert result.exit_code == 0

        slug = slugify("Super Bot")
        content = (project_dir / f"src/{slug}/graph.py").read_text()
        assert "Super Bot" in content
