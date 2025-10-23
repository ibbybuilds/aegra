"""Integration tests for TypeScript graph execution.

These tests require Node.js or Bun to be installed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agent_server.services.langgraph_service import LangGraphService

pytestmark = pytest.mark.asyncio


class TestTypeScriptGraphLoading:
    """Test TypeScript graph loading and detection."""

    async def test_detects_typescript_graph(self, tmp_path):
        """Should detect and register TypeScript graphs."""
        # Create test config
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "ts_agent": "./graphs/ts_example_agent/graph.ts:graph"
            },
            "node_version": "20"
        }""")

        service = LangGraphService(str(config_file))

        # Mock database initialization to test only graph detection
        with patch.object(
            service, "_ensure_default_assistants", new_callable=AsyncMock
        ):
            await service.initialize()

        # Check registry
        graphs = service.list_graphs()
        assert "ts_agent" in graphs
        assert graphs["ts_agent"] == "./graphs/ts_example_agent/graph.ts"

    async def test_typescript_graph_has_correct_type(self, tmp_path):
        """TypeScript graphs should be marked with correct type."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "ts_agent": "./graphs/ts_example_agent/graph.ts:graph"
            }
        }""")

        service = LangGraphService(str(config_file))

        # Mock database initialization
        with patch.object(
            service, "_ensure_default_assistants", new_callable=AsyncMock
        ):
            await service.initialize()

        graph_info = service._graph_registry["ts_agent"]
        assert graph_info["type"] == "typescript"


class TestMixedGraphSupport:
    """Test running both Python and TypeScript graphs."""

    async def test_loads_both_python_and_typescript(self, tmp_path):
        """Should handle mixed Python/TypeScript configuration."""
        config_file = tmp_path / "aegra.json"
        config_file.write_text("""{
            "graphs": {
                "py_agent": "./graphs/react_agent/graph.py:graph",
                "ts_agent": "./graphs/ts_example_agent/graph.ts:graph"
            },
            "node_version": "20"
        }""")

        service = LangGraphService(str(config_file))

        # Mock database initialization
        with patch.object(
            service, "_ensure_default_assistants", new_callable=AsyncMock
        ):
            await service.initialize()

        # Both should be registered
        graphs = service._graph_registry
        assert "py_agent" in graphs
        assert "ts_agent" in graphs

        # Types should be correct
        assert graphs["py_agent"]["type"] == "python"
        assert graphs["ts_agent"]["type"] == "typescript"


@pytest.mark.skipif(
    not Path("graphs/ts_example_agent/graph.ts").exists(),
    reason="TypeScript example graph not found",
)
class TestTypeScriptGraphExecution:
    """Test actual TypeScript graph execution.

    These tests require:
    - Node.js 20+ or Bun installed
    - Dependencies installed in graphs/ts_example_agent/
    """

    async def test_typescript_graph_wrapper_creation(self):
        """Should create TypeScript graph wrapper."""
        service = LangGraphService("aegra.json")

        # Mock database initialization
        with patch.object(
            service, "_ensure_default_assistants", new_callable=AsyncMock
        ):
            await service.initialize()

        if "ts_agent" not in service._graph_registry:
            pytest.skip("ts_agent not configured in aegra.json")

        graph = await service.get_graph("ts_agent")

        # Should return wrapper, not actual graph
        assert hasattr(graph, "is_typescript")
        assert graph.is_typescript is True
        assert hasattr(graph, "runtime")

    async def test_typescript_runtime_initialization(self):
        """Should initialize TypeScript runtime on demand."""
        service = LangGraphService("aegra.json")

        # Mock database initialization
        with patch.object(
            service, "_ensure_default_assistants", new_callable=AsyncMock
        ):
            await service.initialize()

        if "ts_agent" not in service._graph_registry:
            pytest.skip("ts_agent not configured")

        # Runtime should be None initially
        assert service._ts_runtime is None

        # Getting TS graph should initialize runtime
        _ = await service.get_graph("ts_agent")
        assert service._ts_runtime is not None
