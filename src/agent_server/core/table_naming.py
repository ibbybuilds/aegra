"""Helpers for configurable database table names.

We support isolating Aegra's Agent Protocol tables from other schemas (e.g.
LangGraph) by prefixing all Aegra-managed tables and indexes.

Set `AEGRA_TABLE_PREFIX` (e.g. "aegra_") to enable.
"""

from __future__ import annotations

import os


def table_prefix() -> str:
    """Return the configured table prefix (may be empty)."""
    return os.getenv("AEGRA_TABLE_PREFIX", "")


def table_name(base_name: str) -> str:
    """Return the fully qualified table name for a given base name."""
    return f"{table_prefix()}{base_name}"


def index_name(base_index_name: str) -> str:
    """Return the index name, prefixed when a table prefix is configured.

    Postgres index names are schema-global, so prefixing avoids collisions when
    running multiple systems in the same schema.
    """
    prefix = table_prefix()
    return f"{prefix}{base_index_name}" if prefix else base_index_name

