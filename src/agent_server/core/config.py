"""Configuration parser with TypeScript support.

This module extends aegra.json parsing to support both Python and TypeScript graphs,
inspired by LangGraph CLI's configuration handling.
"""

import json
from pathlib import Path
from typing import Any, Literal

MIN_NODE_VERSION = "20"
DEFAULT_NODE_VERSION = "20"


def is_node_graph(graph_spec: str) -> bool:
    """Check if a graph is a TypeScript/JavaScript graph based on file extension.

    Reuses logic from LangGraph CLI (langgraph/libs/cli/langgraph_cli/config.py:589-604)

    Args:
        graph_spec: Graph path specification (e.g., "./graphs/agent.ts:graph")

    Returns:
        True if the graph is a TypeScript/JavaScript graph, False otherwise
    """
    # Extract file path from spec (format: "path/to/file.ext:export_name")
    file_path = graph_spec.split(":")[0] if ":" in graph_spec else graph_spec
    file_ext = Path(file_path).suffix

    # TypeScript/JavaScript extensions
    return file_ext in [
        ".ts",  # TypeScript
        ".mts",  # TypeScript module
        ".cts",  # TypeScript CommonJS
        ".js",  # JavaScript
        ".mjs",  # JavaScript module
        ".cjs",  # JavaScript CommonJS
    ]


def validate_node_version(version: str) -> int:
    """Parse and validate Node.js version.

    Args:
        version: Node.js version string (e.g., "20")

    Returns:
        Major version number

    Raises:
        ValueError: If version format is invalid or too old
    """
    try:
        if "." in version:
            raise ValueError("Node.js version must be major version only")
        major = int(version)
    except ValueError as e:
        raise ValueError(
            f"Invalid Node.js version format: {version}. "
            "Use major version only (e.g., '20')."
        ) from e

    min_major = int(MIN_NODE_VERSION)
    if major < min_major:
        raise ValueError(
            f"Node.js version {version} is not supported. "
            f"Minimum required version is {MIN_NODE_VERSION}."
        )

    return major


class AegraConfig:
    """Configuration loader and validator for aegra.json with TypeScript support."""

    def __init__(self, config_path: str | Path = "aegra.json"):
        """Initialize configuration loader.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self._has_node_graphs: bool = False
        self._has_python_graphs: bool = False

    def load(self) -> dict[str, Any]:
        """Load and validate configuration file.

        Returns:
            Validated configuration dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If configuration is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with self.config_path.open() as f:
            self.config = json.load(f)

        self._validate()
        return self.config

    def _validate(self):
        """Validate configuration structure and values."""
        # Analyze graph types
        graphs = self.config.get("graphs", {})
        if not graphs:
            raise ValueError("No graphs found in configuration")

        for _graph_id, graph_spec in graphs.items():
            if is_node_graph(graph_spec):
                self._has_node_graphs = True
            else:
                self._has_python_graphs = True

        # Validate node_version if present or required
        node_version = self.config.get("node_version")
        if node_version:
            validate_node_version(node_version)
        elif self._has_node_graphs and not node_version:
            # Auto-set default if TypeScript graphs are present
            self.config["node_version"] = DEFAULT_NODE_VERSION
            print(
                f"ℹ️  No node_version specified, using default: {DEFAULT_NODE_VERSION}"
            )

    def has_node_graphs(self) -> bool:
        """Check if configuration contains TypeScript/JavaScript graphs."""
        return self._has_node_graphs

    def has_python_graphs(self) -> bool:
        """Check if configuration contains Python graphs."""
        return self._has_python_graphs

    def get_node_version(self) -> str | None:
        """Get configured Node.js version."""
        return self.config.get("node_version")

    def get_graphs(self) -> dict[str, str]:
        """Get all graph definitions."""
        return self.config.get("graphs", {})

    def get_graph_type(self, graph_id: str) -> Literal["python", "typescript"]:
        """Get the type of a specific graph.

        Args:
            graph_id: Graph identifier

        Returns:
            "python" or "typescript"

        Raises:
            KeyError: If graph_id doesn't exist
        """
        graphs = self.get_graphs()
        if graph_id not in graphs:
            raise KeyError(f"Graph not found: {graph_id}")

        return "typescript" if is_node_graph(graphs[graph_id]) else "python"
