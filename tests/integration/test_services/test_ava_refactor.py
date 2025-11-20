"""Integration tests for AVA agent refactor.

Tests that AVA agent works like other graphs:
- Loads via langgraph_service.get_graph()
- Uses runtime.context pattern
- Is cached and reused
- No special handling needed
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent_server.services.langgraph_service import LangGraphService


@pytest.mark.asyncio
class TestAVAAgentLoading:
    """Test that AVA agent loads correctly via factory method."""

    async def test_ava_loads_via_get_graph(self):
        """Test that AVA loads through the standard get_graph() method."""
        # Mock database and _ensure_default_assistants
        with (
            patch.object(
                LangGraphService, "_ensure_default_assistants", new_callable=AsyncMock
            ),
            patch("src.agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(
                return_value="mock_checkpointer"
            )
            mock_db_manager.get_store = AsyncMock(return_value="mock_store")

            service = LangGraphService()
            await service.initialize()

            # AVA should be in the registry
            assert "ava" in service._graph_registry

            # Should be able to load it
            graph = await service.get_graph("ava")
            assert graph is not None

            # Should be cached after first load
            assert "ava" in service._graph_cache

    async def test_ava_cached_after_first_load(self):
        """Test that AVA is cached after first load."""
        # Mock database and _ensure_default_assistants
        with (
            patch.object(
                LangGraphService, "_ensure_default_assistants", new_callable=AsyncMock
            ),
            patch("src.agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(
                return_value="mock_checkpointer"
            )
            mock_db_manager.get_store = AsyncMock(return_value="mock_store")

            service = LangGraphService()
            await service.initialize()

            # Clear cache
            service._graph_cache.clear()

            # First load
            graph1 = await service.get_graph("ava")

            # Second load should use cache
            with patch.object(service, "_load_graph_from_file") as mock_load:
                graph2 = await service.get_graph("ava")
                # Should not call _load_graph_from_file again
                mock_load.assert_not_called()
                # Should return same graph instance
                assert graph1 is graph2

    async def test_ava_works_like_other_graphs(self):
        """Test that AVA follows the same loading pattern as other graphs."""
        # Mock database and _ensure_default_assistants
        with (
            patch.object(
                LangGraphService, "_ensure_default_assistants", new_callable=AsyncMock
            ),
            patch("src.agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(
                return_value="mock_checkpointer"
            )
            mock_db_manager.get_store = AsyncMock(return_value="mock_store")

            service = LangGraphService()
            await service.initialize()

            # Load AVA graph
            ava_graph = await service.get_graph("ava")

            # Should be loaded
            assert ava_graph is not None

            # Should be cached
            assert "ava" in service._graph_cache

            # Should be in registry (same as other graphs)
            assert "ava" in service._graph_registry

            # Verify it uses the same loading mechanism by checking cache behavior
            # Second call should use cache
            ava_graph2 = await service.get_graph("ava")
            assert ava_graph is ava_graph2  # Same instance from cache


class TestAVAContextHandling:
    """Test that AVA context is handled correctly."""

    def test_ava_context_extraction(self):
        """Test that AVA context is extracted from nested structure."""
        from src.agent_server.utils.context_parser import parse_context_for_graph

        context = {
            "call_context": {
                "type": "property_specific",
                "property": {"property_id": "prop_123", "property_name": "Grand Hotel"},
            }
        }

        result = parse_context_for_graph("ava", context)

        # Should extract call_context
        assert result == context["call_context"]
        assert result["type"] == "property_specific"

    def test_ava_context_passed_to_runtime(self):
        """Test that extracted context is passed to graph.astream()."""
        from src.agent_server.utils.context_parser import parse_context_for_graph

        context = {"call_context": {"type": "general"}}

        parsed = parse_context_for_graph("ava", context)

        # Should be a dict ready for runtime.context
        assert isinstance(parsed, dict)
        assert parsed["type"] == "general"

    def test_ava_context_none_handled(self):
        """Test that None context is handled gracefully."""
        from src.agent_server.utils.context_parser import parse_context_for_graph

        result = parse_context_for_graph("ava", None)
        assert result is None


class TestAVANoSpecialHandling:
    """Test that AVA requires no special handling in runs.py."""

    def test_ava_no_special_case_in_runs(self):
        """Test that runs.py doesn't have special cases for AVA."""
        # Read the runs.py file and check for special cases
        import inspect

        from src.agent_server.api import runs

        source = inspect.getsource(runs.execute_run_async)

        # Should not have special case for AVA (check for old pattern)
        # Note: We check that there's no special handling that creates agent per request
        assert "create_ava_agent" not in source, (
            "AVA should not have special agent creation in execute_run_async"
        )

        # Should use standard get_graph() for all graphs
        assert "langgraph_service.get_graph(graph_id)" in source

    def test_ava_context_parsing_unified(self):
        """Test that AVA context parsing is unified with other graphs."""
        from src.agent_server.utils.context_parser import parse_context_for_graph

        # Both should be callable
        ava_result = parse_context_for_graph(
            "ava", {"call_context": {"type": "general"}}
        )
        other_result = parse_context_for_graph("react_agent", {"some_key": "value"})

        # Both should return dicts
        assert isinstance(ava_result, dict)
        assert isinstance(other_result, dict)
