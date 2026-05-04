"""Unit tests for _resolve_sort and filter merging in /assistants/search."""

import pytest
from pydantic import ValidationError

from aegra_api.api.assistants import (
    _merge_handler_filters_into_metadata,
    _resolve_sort,
)
from aegra_api.core.orm import Assistant as AssistantORM
from aegra_api.models import AssistantSearchRequest


def _col_name(column: object) -> str:
    return getattr(column, "key", None) or getattr(column, "name", "")


class TestResolveSort:
    """_resolve_sort honours sort_by / sort_order."""

    def test_default_is_created_at_desc(self) -> None:
        column, asc = _resolve_sort(AssistantSearchRequest())
        assert _col_name(column) == "created_at"
        assert asc is False

    def test_sort_by_defaults_to_desc(self) -> None:
        column, asc = _resolve_sort(AssistantSearchRequest(sort_by="updated_at"))
        assert _col_name(column) == "updated_at"
        assert asc is False

    def test_sort_by_asc(self) -> None:
        column, asc = _resolve_sort(AssistantSearchRequest(sort_by="name", sort_order="asc"))
        assert _col_name(column) == "name"
        assert asc is True

    def test_sort_by_desc_explicit(self) -> None:
        column, asc = _resolve_sort(AssistantSearchRequest(sort_by="assistant_id", sort_order="desc"))
        assert _col_name(column) == "assistant_id"
        assert asc is False

    def test_returns_real_orm_column(self) -> None:
        column, _ = _resolve_sort(AssistantSearchRequest(sort_by="updated_at"))
        assert column is AssistantORM.updated_at


class TestSortByValidation:
    """Pydantic validates sort_by against the Literal at request boundary."""

    def test_invalid_sort_by_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssistantSearchRequest(sort_by="password; DROP TABLE assistants --")  # type: ignore[arg-type]

    def test_invalid_sort_order_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssistantSearchRequest(sort_by="name", sort_order="sideways")  # type: ignore[arg-type]


class TestMergeHandlerFilters:
    """Auth-handler filters are merged into request.metadata, not a non-existent
    request.filters attribute (regression test for #333)."""

    def test_no_filters_no_value_metadata_leaves_metadata_alone(self) -> None:
        request = AssistantSearchRequest(metadata={"keep": "me"})
        _merge_handler_filters_into_metadata(request, None, {})
        assert request.metadata == {"keep": "me"}

    def test_handler_returns_flat_filters_merges_into_metadata(self) -> None:
        """Handler returning ``{"owner": "u1"}`` becomes a metadata containment filter."""
        request = AssistantSearchRequest(metadata={"env": "prod"})
        _merge_handler_filters_into_metadata(request, {"owner": "u1"}, {})
        assert request.metadata == {"env": "prod", "owner": "u1"}

    def test_handler_returns_metadata_key_unwraps_it(self) -> None:
        """Handler returning ``{"metadata": {"owner": "u1"}}`` is unwrapped, not nested."""
        request = AssistantSearchRequest(metadata={"env": "prod"})
        _merge_handler_filters_into_metadata(request, {"metadata": {"owner": "u1"}}, {})
        assert request.metadata == {"env": "prod", "owner": "u1"}

    def test_handler_mutated_value_metadata_is_picked_up(self) -> None:
        """Handler that mutates ``value['metadata']`` instead of returning is honoured."""
        request = AssistantSearchRequest(metadata={"env": "prod"})
        value = {"metadata": {"owner": "u1"}}
        _merge_handler_filters_into_metadata(request, None, value)
        assert request.metadata == {"env": "prod", "owner": "u1"}

    def test_request_filters_attribute_does_not_exist(self) -> None:
        """The bug in #333 was code referencing a non-existent ``filters`` field;
        confirm the model still has no such attribute so we don't regress."""
        assert "filters" not in AssistantSearchRequest.model_fields

    def test_handler_filters_override_request_metadata(self) -> None:
        """When keys conflict, handler filters win (auth must not be bypassable)."""
        request = AssistantSearchRequest(metadata={"owner": "attacker"})
        _merge_handler_filters_into_metadata(request, {"owner": "real-user"}, {})
        assert request.metadata == {"owner": "real-user"}
