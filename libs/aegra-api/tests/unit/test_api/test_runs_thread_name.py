"""Unit tests for _extract_thread_name helper in runs.py."""

from aegra_api.api.runs import _extract_thread_name


class TestExtractThreadName:
    """Test _extract_thread_name helper."""

    def test_returns_empty_for_no_messages(self) -> None:
        assert _extract_thread_name({}) == ""

    def test_returns_empty_for_empty_messages_list(self) -> None:
        assert _extract_thread_name({"messages": []}) == ""

    def test_returns_empty_for_non_list_messages(self) -> None:
        assert _extract_thread_name({"messages": "not a list"}) == ""

    def test_extracts_content_from_dict_message(self) -> None:
        result = _extract_thread_name(
            {"messages": [{"role": "human", "content": "Hello world"}]}
        )
        assert result == "Hello world"

    def test_extracts_first_message_with_content(self) -> None:
        result = _extract_thread_name(
            {
                "messages": [
                    {"role": "human", "content": "First message"},
                    {"role": "ai", "content": "Response"},
                ]
            }
        )
        assert result == "First message"

    def test_skips_messages_without_content(self) -> None:
        result = _extract_thread_name(
            {
                "messages": [
                    {"role": "system"},
                    {"role": "human", "content": "Actual question"},
                ]
            }
        )
        assert result == "Actual question"

    def test_skips_empty_string_content(self) -> None:
        result = _extract_thread_name(
            {
                "messages": [
                    {"role": "human", "content": "   "},
                    {"role": "human", "content": "Real content"},
                ]
            }
        )
        assert result == "Real content"

    def test_truncates_long_content_at_word_boundary(self) -> None:
        long_content = "word " * 30  # 150 chars
        result = _extract_thread_name({"messages": [{"content": long_content}]})
        assert result.endswith("...")
        assert len(result) <= 104  # 100 + "..."

    def test_handles_langchain_message_objects(self) -> None:
        class FakeMessage:
            content = "Object message"

        result = _extract_thread_name({"messages": [FakeMessage()]})
        assert result == "Object message"

    def test_returns_empty_for_none_content(self) -> None:
        result = _extract_thread_name(
            {"messages": [{"role": "human", "content": None}]}
        )
        assert result == ""

    def test_returns_empty_for_non_string_content(self) -> None:
        result = _extract_thread_name(
            {"messages": [{"role": "human", "content": 42}]}
        )
        assert result == ""
