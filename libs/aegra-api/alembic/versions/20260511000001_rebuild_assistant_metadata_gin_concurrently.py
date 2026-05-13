"""Rebuild idx_assistant_metadata_gin without a SHARE lock

The original ``c8d9e0f1a234`` migration created this GIN index inside
Alembic's transaction, which acquires a ``SHARE`` lock on ``assistant`` for
the full build. On large assistant tables that lock window blocks every
concurrent INSERT/UPDATE/DELETE — a write-side stall on every deploy that
runs the migration.

This migration drops and recreates the index via ``CREATE INDEX
CONCURRENTLY``. Mirrors the thread.metadata_json rebuild in revision
``d9e0f1a23456``. See that revision for the autocommit-block / INVALID-index
recovery notes; the same pattern applies here.

Revision ID: e0f1a234b567
Revises: d9e0f1a23456
Create Date: 2026-05-11 00:00:00.000001

"""

from alembic import op

revision = "e0f1a234b567"
down_revision = "d9e0f1a23456"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_assistant_metadata_gin"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX_NAME} ON assistant USING gin (metadata jsonb_path_ops)")


def downgrade() -> None:
    # Restore the index so the schema state at d9e0f1a23456 still has the
    # GIN predicate /assistants/search relies on. See the thread rebuild
    # for the rebuild-via-CONCURRENTLY rationale.
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX_NAME} ON assistant USING gin (metadata jsonb_path_ops)")
