"""Add GIN jsonb_path_ops index on thread.metadata_json

Backs the JSONB containment predicate ``metadata_json @> :filter`` used by
``POST /threads/search`` for metadata filtering. ``jsonb_path_ops`` is smaller
and faster than the default ``jsonb_ops`` for containment-only queries (no
key-existence support, which we don't need here).

Revision ID: b7c8d9e0f123
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c8d9e0f123"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_thread_metadata_gin"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "thread",
        ["metadata_json"],
        postgresql_using="gin",
        postgresql_ops={"metadata_json": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="thread")
