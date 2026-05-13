"""Filter compiler for auth-handler return values.

Auth handlers (registered via ``@auth.on.*``) can return a dict of filters
that further restrict the result of search/list endpoints. Before this
compiler, every non-``metadata`` key was stuffed into a JSONB containment
predicate against the resource's ``metadata`` column, which silently produced
empty result sets for two real shapes:

1. **Operator filters** (``{"x": {"$eq": "y"}}``, ``{"p": {"$contains": "u"}}``)
   — Postgres asked "does metadata contain this literal operator dict?" Never
   true.
2. **Top-level column filters** (``{"graph_id": "agent-v2"}``) — unless every
   row mirrored ``graph_id`` inside its metadata JSONB, the predicate matched
   nothing.

This module compiles handler filters into two output channels:

- ``column_filters``: exact-match constraints for whitelisted top-level
  columns. Always AND'd with user-supplied filters at the service layer, so
  the handler restricts the user's view (intended security semantics).
- ``metadata_containment``: a JSONB payload used in ``metadata @> :value``.
  Continues to back the common ``{"owner": user_id}`` case where the value
  lives inside the entity's metadata JSONB.

Unrepresentable operators (``$ne``, ``$gt``, unknown ``$xxx``) raise
``HTTPException(400)`` rather than silently dropping the predicate, so
handler authors learn about the misconfiguration on the first request
instead of debugging empty result sets in production.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

KNOWN_OPERATORS: frozenset[str] = frozenset({"$eq", "$contains"})


_WHITELISTED_COLUMNS: dict[str, frozenset[str]] = {
    "assistants": frozenset({"graph_id", "name"}),
    "threads": frozenset({"status"}),
}


@dataclass(frozen=True)
class CompiledHandlerFilters:
    """Compiled form of an auth handler's filter dict.

    ``column_filters`` keys are subset of ``_WHITELISTED_COLUMNS[resource]``.
    ``metadata_containment`` is a single dict to use as the right-hand side
    of a ``metadata @> :value`` predicate.
    """

    column_filters: dict[str, Any] = field(default_factory=dict)
    metadata_containment: dict[str, Any] = field(default_factory=dict)


def compile_handler_filters(
    filters: Mapping[str, Any] | None,
    *,
    resource: str,
) -> CompiledHandlerFilters:
    """Compile an auth handler's return value into safe SQL inputs.

    Recognized per-key operators:

    - ``$eq``: exact match (column or metadata)
    - ``$contains``: JSONB array containment (metadata only)

    Plain (non-operator) values keep their existing semantics: equality for
    columns, containment for metadata.

    Raises ``HTTPException(400)`` for unrepresentable operators rather than
    silently filtering to zero rows.
    """
    if not filters:
        return CompiledHandlerFilters()

    column_whitelist = _WHITELISTED_COLUMNS.get(resource, frozenset())
    columns: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

    nested = filters.get("metadata")
    if isinstance(nested, dict):
        for sub_key, sub_value in nested.items():
            metadata[sub_key] = _compile_value(sub_value, is_column=False, path=f"metadata.{sub_key}")

    for key, raw in filters.items():
        if key == "metadata":
            continue
        if key in column_whitelist:
            columns[key] = _compile_value(raw, is_column=True, path=key)
        else:
            metadata[key] = _compile_value(raw, is_column=False, path=key)

    return CompiledHandlerFilters(column_filters=columns, metadata_containment=metadata)


def _compile_value(raw: Any, *, is_column: bool, path: str) -> Any:
    """Normalize one filter value to its SQL-ready representation.

    Operator dicts collapse to their operand: ``{"$eq": v}`` → ``v``;
    ``{"$contains": v}`` → ``[v]`` so it pairs with JSONB containment.
    Non-dict values and operator-free dicts pass through unchanged.
    """
    if not isinstance(raw, dict):
        return raw

    operators = [k for k in raw if isinstance(k, str) and k.startswith("$")]
    if not operators:
        return raw

    if len(operators) != len(raw):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auth handler filter at {path!r} mixes operator keys ({operators!r}) "
                "with regular keys; choose one shape per filter value."
            ),
        )

    unknown = sorted(op for op in operators if op not in KNOWN_OPERATORS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auth handler filter at {path!r} uses unsupported operator(s) {unknown!r}. "
                f"Supported operators: {sorted(KNOWN_OPERATORS)!r}."
            ),
        )

    if len(operators) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auth handler filter at {path!r} declares multiple operators "
                f"({sorted(operators)!r}); only one operator is allowed per filter value."
            ),
        )

    op = operators[0]
    op_value = raw[op]

    if op == "$eq":
        return op_value

    # $contains: only valid for metadata-side predicates (JSONB containment
    # treats {"key": [v]} as "the array at key includes v"). Scalar columns
    # have no analogous semantics, so reject early.
    if is_column:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auth handler filter at {path!r} uses '$contains' on a top-level column; "
                "'$contains' is only supported for metadata array fields."
            ),
        )
    return [op_value]
