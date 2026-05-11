"""Unit tests for compile_handler_filters.

Pins the contract documented at the top of aegra_api/core/auth_filters.py:

- Plain values continue to flow into metadata containment for non-whitelisted
  keys (preserves the post-#348 ``{"owner": user_id}`` shape).
- Whitelisted keys per resource (``graph_id``/``name`` for assistants,
  ``status`` for threads) route to ``column_filters`` instead.
- Operator dicts (``{"$eq": v}``, ``{"$contains": v}``) compile to safe
  operand forms.
- Unrepresentable operators surface as ``HTTPException(400)`` so handler
  authors aren't debugging empty result sets.
"""

import pytest
from fastapi import HTTPException

from aegra_api.core.auth_filters import (
    CompiledHandlerFilters,
    compile_handler_filters,
)


class TestEmptyAndPlainPassthrough:
    """Baseline: empty inputs produce empty outputs; plain shapes preserved."""

    def test_none_returns_empty(self) -> None:
        compiled = compile_handler_filters(None, resource="assistants")
        assert compiled == CompiledHandlerFilters()

    def test_empty_returns_empty(self) -> None:
        compiled = compile_handler_filters({}, resource="assistants")
        assert compiled == CompiledHandlerFilters()

    def test_flat_owner_routes_to_metadata(self) -> None:
        compiled = compile_handler_filters({"owner": "u1"}, resource="assistants")
        assert compiled.column_filters == {}
        assert compiled.metadata_containment == {"owner": "u1"}

    def test_nested_metadata_unwraps(self) -> None:
        compiled = compile_handler_filters({"metadata": {"tenant": "acme"}}, resource="assistants")
        assert compiled.metadata_containment == {"tenant": "acme"}

    def test_nested_metadata_and_flat_keys_merge(self) -> None:
        """Handlers can return both shapes in one dict; both apply."""
        compiled = compile_handler_filters({"metadata": {"tenant": "acme"}, "owner": "u1"}, resource="assistants")
        assert compiled.metadata_containment == {"tenant": "acme", "owner": "u1"}


class TestColumnRouting:
    """Whitelisted top-level keys go to column_filters, not metadata."""

    def test_assistants_graph_id_is_a_column(self) -> None:
        compiled = compile_handler_filters({"graph_id": "agent-v2"}, resource="assistants")
        assert compiled.column_filters == {"graph_id": "agent-v2"}
        assert compiled.metadata_containment == {}

    def test_assistants_name_is_a_column(self) -> None:
        compiled = compile_handler_filters({"name": "prod-assistant"}, resource="assistants")
        assert compiled.column_filters == {"name": "prod-assistant"}
        assert compiled.metadata_containment == {}

    def test_threads_status_is_a_column(self) -> None:
        compiled = compile_handler_filters({"status": "idle"}, resource="threads")
        assert compiled.column_filters == {"status": "idle"}
        assert compiled.metadata_containment == {}

    def test_thread_graph_id_is_not_whitelisted(self) -> None:
        """graph_id is whitelisted for assistants but not for threads."""
        compiled = compile_handler_filters({"graph_id": "agent-v2"}, resource="threads")
        assert compiled.column_filters == {}
        assert compiled.metadata_containment == {"graph_id": "agent-v2"}

    def test_columns_and_metadata_coexist(self) -> None:
        compiled = compile_handler_filters({"graph_id": "agent-v2", "owner": "u1"}, resource="assistants")
        assert compiled.column_filters == {"graph_id": "agent-v2"}
        assert compiled.metadata_containment == {"owner": "u1"}

    def test_unknown_resource_treats_all_keys_as_metadata(self) -> None:
        compiled = compile_handler_filters({"graph_id": "x"}, resource="store")
        assert compiled.column_filters == {}
        assert compiled.metadata_containment == {"graph_id": "x"}


class TestOperatorEq:
    """$eq is a no-op alias for plain equality."""

    def test_eq_on_column(self) -> None:
        compiled = compile_handler_filters({"graph_id": {"$eq": "agent-v2"}}, resource="assistants")
        assert compiled.column_filters == {"graph_id": "agent-v2"}

    def test_eq_on_metadata_flat(self) -> None:
        compiled = compile_handler_filters({"owner": {"$eq": "u1"}}, resource="assistants")
        assert compiled.metadata_containment == {"owner": "u1"}

    def test_eq_on_metadata_nested(self) -> None:
        compiled = compile_handler_filters({"metadata": {"tenant": {"$eq": "acme"}}}, resource="assistants")
        assert compiled.metadata_containment == {"tenant": "acme"}


class TestOperatorContains:
    """$contains wraps the operand into a JSONB containment array."""

    def test_contains_on_metadata_flat(self) -> None:
        compiled = compile_handler_filters({"participants": {"$contains": "u1"}}, resource="threads")
        # JSONB containment treats {"participants": ["u1"]} as
        # "the array at .participants includes u1".
        assert compiled.metadata_containment == {"participants": ["u1"]}

    def test_contains_on_metadata_nested(self) -> None:
        compiled = compile_handler_filters({"metadata": {"tags": {"$contains": "ops"}}}, resource="assistants")
        assert compiled.metadata_containment == {"tags": ["ops"]}

    def test_contains_on_column_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            compile_handler_filters({"graph_id": {"$contains": "agent"}}, resource="assistants")
        assert exc.value.status_code == 400
        assert "$contains" in str(exc.value.detail)
        assert "graph_id" in str(exc.value.detail)


class TestUnsupportedOperators:
    """Unknown operators raise 400 instead of silently filtering to zero rows."""

    @pytest.mark.parametrize("operator", ["$ne", "$gt", "$lt", "$in", "$exists", "$or"])
    def test_unknown_operator_raises_400(self, operator: str) -> None:
        with pytest.raises(HTTPException) as exc:
            compile_handler_filters({"owner": {operator: "u1"}}, resource="assistants")
        assert exc.value.status_code == 400
        assert operator in str(exc.value.detail)

    def test_multiple_operators_raise_400(self) -> None:
        """A value like ``{"$eq": "x", "$contains": "y"}`` has ambiguous intent
        — reject rather than guess."""
        with pytest.raises(HTTPException) as exc:
            compile_handler_filters({"owner": {"$eq": "u1", "$contains": "u2"}}, resource="assistants")
        assert exc.value.status_code == 400

    def test_mixing_operator_and_regular_keys_raises_400(self) -> None:
        """``{"$eq": "x", "x": 1}`` is ambiguous — reject."""
        with pytest.raises(HTTPException) as exc:
            compile_handler_filters({"owner": {"$eq": "u1", "extra": "noise"}}, resource="assistants")
        assert exc.value.status_code == 400

    def test_operator_inside_nested_metadata_also_validated(self) -> None:
        with pytest.raises(HTTPException) as exc:
            compile_handler_filters({"metadata": {"x": {"$ne": "y"}}}, resource="assistants")
        assert exc.value.status_code == 400
        assert "$ne" in str(exc.value.detail)


class TestNonOperatorDictsPassThrough:
    """Plain dict values (no ``$`` keys) keep their nested-JSON semantics
    so handlers can still express deep metadata containment when they want
    to bypass the operator vocabulary."""

    def test_plain_nested_dict_is_preserved(self) -> None:
        compiled = compile_handler_filters({"settings": {"region": "eu", "tier": "pro"}}, resource="assistants")
        assert compiled.metadata_containment == {"settings": {"region": "eu", "tier": "pro"}}
