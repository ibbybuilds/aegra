"""Add execution_params and lease columns to runs table

Supports the worker executor architecture:
- execution_params: JSONB storing RunJob serialization so workers can
  reconstruct the job from the database after receiving a run_id via Redis.
- claimed_by: identifies which worker owns a run (lease holder).
- lease_expires_at: when the lease expires; a reaper re-enqueues runs
  whose leases have expired (worker crashed).

Revision ID: a1b2c3d4e5f6
Revises: e7f3a1b2c4d5
Create Date: 2026-03-14 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "e7f3a1b2c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("execution_params", JSONB(), nullable=True))
    op.add_column("runs", sa.Column("claimed_by", sa.Text(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_runs_lease_reaper", "runs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("idx_runs_lease_reaper", table_name="runs")
    op.drop_column("runs", "lease_expires_at")
    op.drop_column("runs", "claimed_by")
    op.drop_column("runs", "execution_params")
