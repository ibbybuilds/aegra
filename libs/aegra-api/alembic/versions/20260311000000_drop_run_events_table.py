"""Drop run_events table

Event replay is now handled by the broker's replay buffer
(in-memory or Redis Lists) instead of PostgreSQL.

Revision ID: e7f3a1b2c4d5
Revises: d042a0ca1cb5
Create Date: 2026-03-11 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "e7f3a1b2c4d5"
down_revision = "d042a0ca1cb5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_run_events_seq", table_name="run_events")
    op.drop_index("idx_run_events_run_id", table_name="run_events")
    op.drop_table("run_events")


def downgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_run_events_run_id", "run_events", ["run_id"])
    op.create_index("idx_run_events_seq", "run_events", ["run_id", "seq"])
