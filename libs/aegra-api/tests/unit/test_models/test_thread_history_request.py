"""Tests for ThreadHistoryRequest model."""

from aegra_api.models.threads import ThreadHistoryRequest


class TestThreadHistoryRequest:
    """Tests for include_values field on ThreadHistoryRequest."""

    def test_include_values_defaults_to_true(self) -> None:
        """include_values defaults to True for backward compatibility."""
        req = ThreadHistoryRequest()
        assert req.include_values is True

    def test_include_values_can_be_set_false(self) -> None:
        """include_values can be explicitly set to False."""
        req = ThreadHistoryRequest(include_values=False)
        assert req.include_values is False

    def test_include_values_can_be_set_true(self) -> None:
        """include_values can be explicitly set to True."""
        req = ThreadHistoryRequest(include_values=True)
        assert req.include_values is True

    def test_full_request_with_include_values_false(self) -> None:
        """All fields work together when include_values is False."""
        req = ThreadHistoryRequest(
            limit=50,
            before="cp-100",
            metadata={"source": "loop"},
            include_values=False,
        )
        assert req.limit == 50
        assert req.before == "cp-100"
        assert req.metadata == {"source": "loop"}
        assert req.include_values is False
