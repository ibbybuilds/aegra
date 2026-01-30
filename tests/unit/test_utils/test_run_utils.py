import pytest


def test_merge_jsonb():
    # Import inside test to ensure package import resolution in test env
    from agent_server.utils.run_utils import _merge_jsonb

    # _merge_jsonb should merge dicts and ignore None
    a = {"x": 1, "y": {"a": 2}}
    b = {"y": {"b": 3}, "z": 4}
    merged = _merge_jsonb(a, None, b)
    assert merged["x"] == 1
    assert merged["z"] == 4
    # b should override a for top-level keys
    assert merged["y"] == {"b": 3}
