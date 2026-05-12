"""Unit tests for JsonbSafe TypeDecorator NULL byte stripping.

Regression cover for issue #370: Postgres JSONB rejects U+0000 with
asyncpg ``UntranslatableCharacterError``. ``JsonbSafe.process_bind_param``
strips NULL bytes recursively at the type boundary so every JSONB column
on the ORM is protected uniformly.
"""

from typing import Any

import pytest

from aegra_api.core.orm import JsonbSafe, _strip_null_bytes


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
