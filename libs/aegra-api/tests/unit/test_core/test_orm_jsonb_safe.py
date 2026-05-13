"""Unit tests for JsonbSafe TypeDecorator NULL byte stripping.

Regression cover for issue #370: Postgres JSONB rejects U+0000 with
asyncpg ``UntranslatableCharacterError``. ``JsonbSafe.process_bind_param``
strips NULL bytes recursively at the type boundary so every JSONB column
on the ORM is protected uniformly.
"""

from typing import Any

import pytest

from aegra_api.core.orm import _MAX_STRIP_DEPTH, JsonbSafe, _strip_null_bytes


class TestStripNullBytes:
    """Recursive NULL byte stripping across nested JSON-compatible structures."""

    def test_clean_string_returned_identical(self) -> None:
        s = "hello world"
        assert _strip_null_bytes(s) is s

    def test_string_with_null_byte_stripped(self) -> None:
        assert _strip_null_bytes("before\x00after") == "beforeafter"

    def test_only_null_bytes(self) -> None:
        assert _strip_null_bytes("\x00\x00\x00") == ""

    def test_other_control_chars_preserved(self) -> None:
        # JSONB only rejects U+0000; other control chars (\n, \t, \x01) are valid.
        s = "line1\nline2\ttab\x01ctrl"
        assert _strip_null_bytes(s) == s

    def test_dict_recursive(self) -> None:
        result = _strip_null_bytes({"a": "x\x00y", "b": {"c": "z\x00"}})
        assert result == {"a": "xy", "b": {"c": "z"}}

    def test_list_recursive(self) -> None:
        assert _strip_null_bytes(["a\x00", "b", ["c\x00d"]]) == ["a", "b", ["cd"]]

    def test_tuple_returned_as_list(self) -> None:
        # JSON has no tuples; serialize as list (matches GeneralSerializer behaviour).
        assert _strip_null_bytes(("a\x00", "b")) == ["a", "b"]

    def test_deeply_nested(self) -> None:
        value = {"k": [{"inner": ["deep\x00val", {"deeper": "x\x00"}]}]}
        expected = {"k": [{"inner": ["deepval", {"deeper": "x"}]}]}
        assert _strip_null_bytes(value) == expected

    @pytest.mark.parametrize("value", [None, 42, 3.14, True, False])
    def test_non_string_scalars_passthrough(self, value: Any) -> None:
        assert _strip_null_bytes(value) is value

    def test_dict_keys_with_null_byte_stripped(self) -> None:
        # NULL bytes in keys are also illegal in JSONB text; strip both sides.
        result = _strip_null_bytes({"key\x00": "value"})
        assert result == {"key": "value"}


class TestJsonbSafeBindParam:
    """The TypeDecorator hook is the only DB-facing surface."""

    def test_process_bind_param_strips_nulls(self) -> None:
        col = JsonbSafe()
        result = col.process_bind_param({"out": "a\x00b"}, dialect=None)  # type: ignore[arg-type]
        assert result == {"out": "ab"}

    def test_process_bind_param_none_passthrough(self) -> None:
        col = JsonbSafe()
        assert col.process_bind_param(None, dialect=None) is None  # type: ignore[arg-type]

    def test_cache_ok_set(self) -> None:
        # SQLAlchemy requires cache_ok on user-defined TypeDecorators to participate
        # in statement caching; without it every statement is re-compiled.
        assert JsonbSafe.cache_ok is True


class TestDepthGuard:
    """Recursion stops at _MAX_STRIP_DEPTH to avoid RecursionError on adversarial payloads."""

    def test_depth_within_limit_processed(self) -> None:
        # Build a nested chain just under the limit; stripping must still work.
        depth = _MAX_STRIP_DEPTH - 10
        value: Any = "leaf\x00"
        for _ in range(depth):
            value = [value]
        result = _strip_null_bytes(value)
        # Walk down to leaf and verify it was stripped.
        cursor = result
        for _ in range(depth):
            cursor = cursor[0]
        assert cursor == "leaf"

    def test_depth_overflow_returns_untouched(self, caplog: pytest.LogCaptureFixture) -> None:
        # Build a payload deeper than the guard; deepest values must come back
        # unchanged (no RecursionError, no infinite loop).
        depth = _MAX_STRIP_DEPTH + 50
        value: Any = "leaf\x00"
        for _ in range(depth):
            value = [value]
        result = _strip_null_bytes(value)
        # First _MAX_STRIP_DEPTH levels were entered; below that, value returned
        # as-is. We don't assert the exact pivot, only that no exception fired
        # and the result is structurally a list (recursion didn't crash).
        assert isinstance(result, list)


class TestKeyCollisionWarning:
    """Stripped-key collisions must log a warning so silent data loss is visible."""

    def test_collision_logs_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch the module-level structlog logger to capture warning calls
        # without relying on the structlog config (caplog only sees stdlib logs).
        from aegra_api.core import orm

        calls: list[tuple[str, dict[str, Any]]] = []

        def _record(event: str, **kw: Any) -> None:
            calls.append((event, kw))

        monkeypatch.setattr(orm._logger, "warning", _record)
        result = orm._strip_null_bytes({"a\x00": "first", "a": "second"})
        assert result == {"a": "second"}
        assert any(event == "jsonb_strip_key_collision" for event, _ in calls)

    def test_no_collision_no_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aegra_api.core import orm

        calls: list[str] = []
        monkeypatch.setattr(orm._logger, "warning", lambda event, **kw: calls.append(event))
        orm._strip_null_bytes({"a\x00": "v1", "b": "v2"})
        assert "jsonb_strip_key_collision" not in calls
