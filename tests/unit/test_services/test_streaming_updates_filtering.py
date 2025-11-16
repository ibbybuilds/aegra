"""Unit tests for updates filtering and final_output tracking in streaming"""

from src.agent_server.services.streaming_service import StreamingService


class TestUpdatesFiltering:
    """Test updates events filtering logic"""

    def setup_method(self):
        """Setup test fixtures"""
        self.service = StreamingService()

    def test_process_interrupt_updates_2_tuple_with_interrupt(self):
        """Test processing 2-tuple interrupt updates event"""
        raw_event = ("updates", {"__interrupt__": [{"node": "test"}]})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == ("values", {"__interrupt__": [{"node": "test"}]})

    def test_process_interrupt_updates_2_tuple_without_interrupt(self):
        """Test processing 2-tuple non-interrupt updates event"""
        raw_event = ("updates", {"node": "test", "data": "value"})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is True
        assert processed == raw_event

    def test_process_interrupt_updates_3_tuple_with_interrupt_subgraphs(self):
        """Test processing 3-tuple interrupt updates event with subgraphs"""
        raw_event = (["subagent"], "updates", {"__interrupt__": [{"node": "test"}]})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == (
            ["subagent"],
            "values",
            {"__interrupt__": [{"node": "test"}]},
        )

    def test_process_interrupt_updates_3_tuple_without_interrupt_subgraphs(self):
        """Test processing 3-tuple non-interrupt updates event with subgraphs"""
        raw_event = (["subagent"], "updates", {"node": "test", "data": "value"})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is True
        assert processed == raw_event

    def test_process_interrupt_updates_3_tuple_string_namespace(self):
        """Test processing 3-tuple with string namespace"""
        raw_event = ("subagent", "updates", {"__interrupt__": [{"node": "test"}]})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == (
            "subagent",
            "values",
            {"__interrupt__": [{"node": "test"}]},
        )

    def test_process_interrupt_updates_not_only_interrupt_mode(self):
        """Test that updates pass through when only_interrupt_updates=False"""
        raw_event = ("updates", {"node": "test", "data": "value"})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=False
        )

        assert should_skip is False
        assert processed == raw_event

    def test_process_interrupt_updates_non_updates_event(self):
        """Test that non-updates events pass through unchanged"""
        raw_event = ("values", {"data": "test"})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == raw_event

    def test_process_interrupt_updates_empty_interrupt_list(self):
        """Test that updates with empty interrupt list are skipped"""
        raw_event = ("updates", {"__interrupt__": []})
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is True
        assert processed == raw_event

    def test_process_interrupt_updates_non_tuple_event(self):
        """Test that non-tuple events pass through unchanged"""
        raw_event = {"data": "test"}
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == raw_event

    def test_process_interrupt_updates_invalid_tuple_length(self):
        """Test that invalid tuple lengths pass through unchanged"""
        raw_event = ("updates",)  # Single element tuple
        processed, should_skip = self.service._process_interrupt_updates(
            raw_event, only_interrupt_updates=True
        )

        assert should_skip is False
        assert processed == raw_event
