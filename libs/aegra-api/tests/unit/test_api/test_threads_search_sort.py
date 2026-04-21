"""Unit tests for _resolve_sort in /threads/search."""

from aegra_api.api.threads import _resolve_sort
from aegra_api.core.orm import Thread as ThreadORM
from aegra_api.models import ThreadSearchRequest


def _col_name(column: object) -> str:
    return getattr(column, "key", None) or getattr(column, "name", "")


class TestResolveSortOrderBy:
    """_resolve_sort parses the legacy order_by single-string form."""

    def test_defaults_to_created_at_desc_when_empty(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by=None))
        assert _col_name(column) == "created_at"
        assert asc is False

    def test_parses_order_by_asc(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by="updated_at ASC"))
        assert _col_name(column) == "updated_at"
        assert asc is True

    def test_parses_order_by_desc(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by="thread_id DESC"))
        assert _col_name(column) == "thread_id"
        assert asc is False

    def test_column_only_defaults_to_desc(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by="status"))
        assert _col_name(column) == "status"
        assert asc is False

    def test_case_insensitive(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by="UPDATED_AT asc"))
        assert _col_name(column) == "updated_at"
        assert asc is True

    def test_falls_back_on_unknown_column(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by="nonexistent_col"))
        assert _col_name(column) == "created_at"
        assert asc is False

    def test_falls_back_on_sql_injection_attempt(self) -> None:
        column, asc = _resolve_sort(
            ThreadSearchRequest(order_by="password; DROP TABLE users --")
        )
        assert _col_name(column) == "created_at"
        assert asc is False

    def test_falls_back_on_empty_string(self) -> None:
        column, asc = _resolve_sort(ThreadSearchRequest(order_by=""))
        assert _col_name(column) == "created_at"
        assert asc is False

    def test_returns_real_orm_column(self) -> None:
        column, _ = _resolve_sort(ThreadSearchRequest(order_by="updated_at ASC"))
        assert column is ThreadORM.updated_at
