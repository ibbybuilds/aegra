"""add_cascade_delete_for_runs_thread_fkey

Revision ID: 11b2402d4be1
Revises: 5931cd77e93b
Create Date: 2025-08-31 17:45:11.723042

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "11b2402d4be1"
down_revision = "5931cd77e93b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to runs.thread_id foreign key constraint."""

    # Drop the existing foreign key constraint
    op.drop_constraint("runs_thread_id_fkey", "runs", type_="foreignkey")

    # Recreate the foreign key constraint with CASCADE DELETE
    op.create_foreign_key(
        "runs_thread_id_fkey",
        "runs",
        "thread",
        ["thread_id"],
        ["thread_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove CASCADE DELETE from runs.thread_id foreign key constraint."""

    # Drop the CASCADE foreign key constraint
    op.drop_constraint("runs_thread_id_fkey", "runs", type_="foreignkey")

    # Recreate the original foreign key constraint without CASCADE
    op.create_foreign_key(
        "runs_thread_id_fkey", "runs", "thread", ["thread_id"], ["thread_id"]
    )
