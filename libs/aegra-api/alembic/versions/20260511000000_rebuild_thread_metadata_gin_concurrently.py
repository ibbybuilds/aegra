"""Rebuild idx_thread_metadata_gin without a SHARE lock

The original ``b7c8d9e0f123`` migration created this GIN index inside
Alembic's transaction, which acquires a ``SHARE`` lock on ``thread`` for the
full build. On large thread tables that lock window blocks every concurrent
INSERT/UPDATE/DELETE — a write-side stall on every deploy that runs the
migration.

This migration drops and recreates the index via ``CREATE INDEX
CONCURRENTLY``, which only holds a ``SHARE UPDATE EXCLUSIVE`` lock and lets
writes proceed during the build. Must run outside a transaction; the
``autocommit_block`` exits the wrapping Alembic transaction for the duration.

Recovery: if ``CREATE INDEX CONCURRENTLY`` is interrupted, Postgres leaves
an INVALID index behind that won't satisfy queries. Drop it and re-run::

    DROP INDEX IF EXISTS idx_thread_metadata_gin;

This migration's ``DROP INDEX CONCURRENTLY IF EXISTS`` handles both the
first-time and the post-failure retry case idempotently.

Revision ID: d9e0f1a23456
Revises: c8d9e0f1a234
Create Date: 2026-05-11 00:00:00.000000

"""

from alembic import op

revision = "d9e0f1a23456"
down_revision = "c8d9e0f1a234"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_thread_metadata_gin"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX_NAME} ON thread USING gin (metadata_json jsonb_path_ops)")


def downgrade() -> None:
    # Restore the index so the schema state at c8d9e0f1a234 still has the
    # GIN predicate /threads/search relies on. We rebuild CONCURRENTLY rather
    # than reproducing the original transactional lock-build — the schema
    # outcome is identical and downgrade should be safe to run live.
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX_NAME} ON thread USING gin (metadata_json jsonb_path_ops)")
