"""migrate_run_status_to_standard_values

Revision ID: d042a0ca1cb5
Revises: aee821a02fc8
Create Date: 2025-11-15 15:24:15.221101

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d042a0ca1cb5"
down_revision = "aee821a02fc8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Migrate legacy Aegra run status values to standard values.

    Mapping:
    - "completed" → "success"
    - "failed" → "error"
    - "cancelled" → "interrupted"
    - "streaming" → "running" (legacy status for active streaming runs)

    Other statuses (pending, running, interrupted, error, success, timeout) remain unchanged.
    """
    # Update completed → success
    op.execute(sa.text("UPDATE runs SET status = 'success' WHERE status = 'completed'"))

    # Update failed → error
    op.execute(sa.text("UPDATE runs SET status = 'error' WHERE status = 'failed'"))

    # Update cancelled → interrupted
    op.execute(sa.text("UPDATE runs SET status = 'interrupted' WHERE status = 'cancelled'"))

    # Update streaming → running (legacy status for active streaming runs)
    op.execute(sa.text("UPDATE runs SET status = 'running' WHERE status = 'streaming'"))


def downgrade() -> None:
    """Revert standard status values back to legacy Aegra values.

    Reverse mapping:
    - "success" → "completed"
    - "error" → "failed"
    - "interrupted" → "cancelled" (only if originally cancelled, but we can't distinguish)
    - "running" → "streaming" (if originally streaming, but we can't distinguish)

    Note: This is a lossy operation - we cannot distinguish between originally
    "cancelled" vs "interrupted" runs, so all "interrupted" will become "cancelled".
    Similarly, we cannot distinguish "running" vs "streaming", so all "running"
    will become "streaming".
    """
    # Update success → completed
    op.execute(sa.text("UPDATE runs SET status = 'completed' WHERE status = 'success'"))

    # Update error → failed
    op.execute(sa.text("UPDATE runs SET status = 'failed' WHERE status = 'error'"))

    # Update interrupted → cancelled
    # Note: This is lossy - we can't distinguish original cancelled vs interrupted
    op.execute(sa.text("UPDATE runs SET status = 'cancelled' WHERE status = 'interrupted'"))

    # Update running → streaming
    # Note: This is lossy - we can't distinguish original running vs streaming
    op.execute(sa.text("UPDATE runs SET status = 'streaming' WHERE status = 'running'"))
