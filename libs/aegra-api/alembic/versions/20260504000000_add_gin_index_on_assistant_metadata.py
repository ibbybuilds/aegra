"""Add GIN jsonb_path_ops index on assistant.metadata

Backs the JSONB containment predicate ``metadata @> :filter`` used by
``POST /assistants/search`` for metadata filtering. ``jsonb_path_ops`` is
smaller and faster than the default ``jsonb_ops`` for containment-only
queries (no key-existence support, which we don't need here). Mirrors the
thread.metadata_json index added in revision b7c8d9e0f123.

Revision ID: c8d9e0f1a234
Revises: b7c8d9e0f123
Create Date: 2026-05-04 00:00:00.000000

"""

from alembic import op

revision = "c8d9e0f1a234"
down_revision = "b7c8d9e0f123"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_assistant_metadata_gin"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "assistant",
        ["metadata"],
        postgresql_using="gin",
        postgresql_ops={"metadata": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="assistant")
