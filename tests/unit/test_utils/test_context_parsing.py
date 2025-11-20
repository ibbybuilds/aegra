"""Tests for context parsing."""
import pytest
from src.agent_server.utils.context_parser import parse_context_for_graph


class TestContextParsing:
    """Test context parsing from API requests."""

    def test_parse_context_for_ava_extracts_call_context(self):
        """Test that AVA context extracts call_context from nested structure."""
        context_dict = {
            "call_context": {
                "type": "property_specific",
                "property": {
                    "property_id": "prop_123",
                    "property_name": "Grand Hotel"
                }
            }
        }
        result = parse_context_for_graph("ava", context_dict)
        # Should extract call_context, not return nested structure
        assert result == context_dict["call_context"]
        assert isinstance(result, dict)
        assert result["type"] == "property_specific"
        assert "property" in result

    def test_parse_context_for_ava_without_call_context(self):
        """Test AVA context parsing when call_context is missing."""
        context_dict = {"some_other_key": "value"}
        result = parse_context_for_graph("ava", context_dict)
        # Should return original dict if call_context not present
        assert result == context_dict

    def test_parse_context_for_other_graphs_passes_through(self):
        """Test that other graphs get raw context dict."""
        context_dict = {"some_key": "some_value"}
        result = parse_context_for_graph("react_agent", context_dict)
        assert result == context_dict
        assert isinstance(result, dict)

    def test_parse_context_for_none(self):
        """Test parsing None context."""
        result = parse_context_for_graph("ava", None)
        assert result is None

    def test_parse_context_for_empty_dict(self):
        """Test parsing empty context dict."""
        result = parse_context_for_graph("ava", {})
        # Empty dict without call_context should return empty dict
        assert result == {}

    def test_parse_context_ava_with_all_context_types(self):
        """Test AVA context parsing with all context types."""
        context_dict = {
            "call_context": {
                "type": "property_specific",
                "property": {
                    "property_id": "prop_123",
                    "property_name": "Grand Hotel",
                    "hotel_id": "hotel_456",
                    "location": "Las Vegas, NV",
                    "features": ["pool", "spa"]
                },
                "booking": {
                    "destination": "Las Vegas",
                    "check_in": "2024-12-15",
                    "check_out": "2024-12-18",
                    "rooms": 1,
                    "adults": 2,
                    "children": 0
                },
                "payment": {
                    "status": "completed",
                    "amount": 299.99,
                    "currency": "USD",
                    "transaction_id": "txn_789"
                },
                "abandoned_payment": {
                    "timestamp": "2024-12-10T10:25:00Z",
                    "amount": 150.00,
                    "currency": "USD",
                    "minutes_ago": 5,
                    "reason": "dropped"
                },
                "session": {
                    "call_reference": "CR123456",
                    "session_legs": [],
                    "previous_interactions": []
                },
                "user_phone": "+1234567890",
                "thread_id": "thread_abc123"
            }
        }
        result = parse_context_for_graph("ava", context_dict)
        assert result == context_dict["call_context"]
        assert result["type"] == "property_specific"
        assert "property" in result
        assert "booking" in result
        assert "payment" in result
        assert "abandoned_payment" in result
