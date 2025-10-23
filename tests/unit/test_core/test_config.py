"""Unit tests for TypeScript configuration parser."""

import pytest

from src.agent_server.core.config import (
    AegraConfig,
    is_node_graph,
    validate_node_version,
)


class TestIsNodeGraph:
    """Test graph type detection."""

    def test_detects_typescript_extensions(self):
        """Should detect TypeScript file extensions."""
        assert is_node_graph("./graphs/agent.ts:graph") is True
        assert is_node_graph("./graphs/agent.mts:graph") is True
        assert is_node_graph("./graphs/agent.cts:graph") is True

    def test_detects_javascript_extensions(self):
        """Should detect JavaScript file extensions."""
        assert is_node_graph("./graphs/agent.js:graph") is True
        assert is_node_graph("./graphs/agent.mjs:graph") is True
        assert is_node_graph("./graphs/agent.cjs:graph") is True

    def test_rejects_python_extensions(self):
        """Should not detect Python files as Node graphs."""
        assert is_node_graph("./graphs/agent.py:graph") is False
        assert is_node_graph("./graphs/agent.pyx:graph") is False

    def test_handles_paths_without_colon(self):
        """Should handle paths without export name."""
        assert is_node_graph("./graphs/agent.ts") is True
        assert is_node_graph("./graphs/agent.py") is False


class TestValidateNodeVersion:
    """Test Node.js version validation."""

    def test_validates_valid_versions(self):
        """Should accept valid Node.js versions."""
        assert validate_node_version("20") == 20
        assert validate_node_version("21") == 21
        assert validate_node_version("22") == 22

    def test_rejects_old_versions(self):
        """Should reject Node.js versions below minimum."""
        with pytest.raises(ValueError, match="not supported"):
            validate_node_version("18")
        with pytest.raises(ValueError, match="not supported"):
            validate_node_version("16")

    def test_rejects_version_with_dots(self):
        """Should reject versions with minor/patch numbers."""
        with pytest.raises(ValueError, match="major version only"):
            validate_node_version("20.0.0")
        with pytest.raises(ValueError, match="major version only"):
            validate_node_version("20.1")

    def test_rejects_invalid_format(self):
        """Should reject non-numeric versions."""
        with pytest.raises(ValueError, match="Invalid Node.js version"):
            validate_node_version("latest")
        with pytest.raises(ValueError, match="Invalid Node.js version"):
            validate_node_version("abc")


class TestAegraConfig:
    """Test configuration loader."""

    def test_detects_mixed_graphs(self, tmp_path):
        """Should detect both Python and TypeScript graphs."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "py_agent": "./graphs/agent.py:graph",
                "ts_agent": "./graphs/agent.ts:graph"
            },
            "node_version": "20"
        }""")

        config = AegraConfig(config_file)
        config.load()

        assert config.has_python_graphs() is True
        assert config.has_node_graphs() is True
        assert config.get_node_version() == "20"

    def test_auto_sets_node_version_for_ts_graphs(self, tmp_path):
        """Should auto-set node_version when TypeScript graphs present."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "ts_agent": "./graphs/agent.ts:graph"
            }
        }""")

        config = AegraConfig(config_file)
        config.load()

        assert config.get_node_version() == "20"  # Default

    def test_get_graph_type(self, tmp_path):
        """Should return correct graph type."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "py_agent": "./graphs/agent.py:graph",
                "ts_agent": "./graphs/agent.ts:graph"
            }
        }""")

        config = AegraConfig(config_file)
        config.load()

        assert config.get_graph_type("py_agent") == "python"
        assert config.get_graph_type("ts_agent") == "typescript"

    def test_raises_on_missing_file(self, tmp_path):
        """Should raise error if config file doesn't exist."""
        config = AegraConfig(tmp_path / "nonexistent.json")
        with pytest.raises(FileNotFoundError):
            config.load()

    def test_raises_on_empty_graphs(self, tmp_path):
        """Should raise error if no graphs defined."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text('{"graphs": {}}')

        config = AegraConfig(config_file)
        with pytest.raises(ValueError, match="No graphs found"):
            config.load()

    def test_raises_on_unknown_graph(self, tmp_path):
        """Should raise error for unknown graph ID."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "agent": "./graphs/agent.py:graph"
            }
        }""")

        config = AegraConfig(config_file)
        config.load()

        with pytest.raises(KeyError):
            config.get_graph_type("unknown")
