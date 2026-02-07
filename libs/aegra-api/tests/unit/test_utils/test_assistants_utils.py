"""Unit tests for assistant utilities"""

from uuid import uuid5

from aegra_api.constants import ASSISTANT_NAMESPACE_UUID
from aegra_api.utils.assistants import resolve_assistant_id


class TestResolveAssistantId:
    """Test resolve_assistant_id function"""

    def test_resolve_graph_id_to_assistant_id(self):
        """Test that graph IDs are converted to deterministic assistant UUIDs"""
        available_graphs = {"agent", "agent_hitl", "subgraph_agent"}

        # Test with a known graph ID
        result = resolve_assistant_id("agent", available_graphs)

        # Should be a UUID derived from the namespace and graph ID
        expected_uuid = str(uuid5(ASSISTANT_NAMESPACE_UUID, "agent"))
        assert result == expected_uuid

        # Should be deterministic
        result2 = resolve_assistant_id("agent", available_graphs)
        assert result == result2

    def test_resolve_unknown_id_as_is(self):
        """Test that unknown IDs are returned as-is"""
        available_graphs = {"agent", "agent_hitl"}

        # Test with an unknown ID
        result = resolve_assistant_id("unknown-graph", available_graphs)

        # Should return the original ID
        assert result == "unknown-graph"

    def test_resolve_assistant_uuid_as_is(self):
        """Test that assistant UUIDs are returned as-is"""
        available_graphs = {"agent", "agent_hitl"}

        # Test with a UUID-like string
        assistant_uuid = "123e4567-e89b-12d3-a456-426614174000"
        result = resolve_assistant_id(assistant_uuid, available_graphs)

        # Should return the original UUID
        assert result == assistant_uuid

    def test_resolve_with_empty_graphs(self):
        """Test resolution with empty graph registry"""
        available_graphs = {}

        result = resolve_assistant_id("agent", available_graphs)

        # Should return the original ID since it's not in the registry
        assert result == "agent"

    def test_resolve_with_dict_graphs(self):
        """Test resolution with dict-based graph registry"""
        available_graphs = {
            "agent": "some_graph_object",
            "agent_hitl": "another_object",
        }

        result = resolve_assistant_id("agent", available_graphs)

        # Should convert to UUID since "agent" is a key in the dict
        expected_uuid = str(uuid5(ASSISTANT_NAMESPACE_UUID, "agent"))
        assert result == expected_uuid

    def test_resolve_case_sensitive(self):
        """Test that resolution is case-sensitive"""
        available_graphs = {"Agent", "agent_hitl"}  # Note capital A

        # Test with lowercase
        result_lower = resolve_assistant_id("agent", available_graphs)
        assert result_lower == "agent"  # Should return as-is

        # Test with uppercase
        result_upper = resolve_assistant_id("Agent", available_graphs)
        expected_uuid = str(uuid5(ASSISTANT_NAMESPACE_UUID, "Agent"))
        assert result_upper == expected_uuid

    def test_resolve_multiple_graphs(self):
        """Test resolution with multiple graph types"""
        available_graphs = {"agent", "agent_hitl", "subgraph_agent", "custom_graph"}

        # Test each graph type
        agent_result = resolve_assistant_id("agent", available_graphs)
        hitl_result = resolve_assistant_id("agent_hitl", available_graphs)
        subgraph_result = resolve_assistant_id("subgraph_agent", available_graphs)
        custom_result = resolve_assistant_id("custom_graph", available_graphs)

        # All should be UUIDs
        assert agent_result == str(uuid5(ASSISTANT_NAMESPACE_UUID, "agent"))
        assert hitl_result == str(uuid5(ASSISTANT_NAMESPACE_UUID, "agent_hitl"))
        assert subgraph_result == str(uuid5(ASSISTANT_NAMESPACE_UUID, "subgraph_agent"))
        assert custom_result == str(uuid5(ASSISTANT_NAMESPACE_UUID, "custom_graph"))

        # Test unknown graph
        unknown_result = resolve_assistant_id("unknown", available_graphs)
        assert unknown_result == "unknown"
