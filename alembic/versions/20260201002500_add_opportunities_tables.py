"""add opportunities and enhanced accountability tables

Revision ID: 8a9c2d4e5f1b
Revises: 65e0089f0cf6
Create Date: 2026-02-01 00:25:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "8a9c2d4e5f1b"
down_revision = "65e0089f0cf6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # DISCOVERED OPPORTUNITIES TABLE
    # =========================================================================
    op.create_table(
        "discovered_opportunities",
        sa.Column(
            "id",
            sa.Text(),
            server_default=sa.text("public.uuid_generate_v4()::text"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "opportunity_type", sa.Text(), nullable=False
        ),  # 'event' or 'job'
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("event_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("salary_range", sa.Text(), nullable=True),
        sa.Column(
            "match_score", sa.Numeric(precision=3, scale=2), nullable=True
        ),  # 0.00 - 1.00
        sa.Column("matched_track", sa.Text(), nullable=True),  # Track that triggered match
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'new'"),
            nullable=False,
        ),  # new, notified, dismissed, applied, expired
        sa.Column(
            "discovered_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_opportunities_user", "discovered_opportunities", ["user_id"], unique=False
    )
    op.create_index(
        "idx_opportunities_status",
        "discovered_opportunities",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_opportunities_type",
        "discovered_opportunities",
        ["opportunity_type"],
        unique=False,
    )
    op.create_index(
        "idx_opportunities_user_status",
        "discovered_opportunities",
        ["user_id", "status"],
        unique=False,
    )

    # =========================================================================
    # USER ACTIVITY TRACKING TABLE (for inactivity detection)
    # =========================================================================
    op.create_table(
        "user_activity_tracking",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("last_login", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_conversation", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_course_activity", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_action_completed", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "current_streak", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "longest_streak", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_streak_date", sa.Date(), nullable=True),
        sa.Column(
            "engagement_score",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # =========================================================================
    # ADD COLUMNS TO USER PREFERENCES
    # =========================================================================
    op.add_column(
        "user_preferences",
        sa.Column("location", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "push_subscription",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # =========================================================================
    # ADD COLUMNS TO ACTION ITEMS (for enhanced reminders)
    # =========================================================================
    op.add_column(
        "action_items",
        sa.Column("advisor_persona", sa.Text(), nullable=True),
    )
    op.add_column(
        "action_items",
        sa.Column(
            "reminder_sent_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "action_items",
        sa.Column("last_reminder_sent", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # =========================================================================
    # ADD COLUMNS TO NOTIFICATIONS (for action buttons)
    # =========================================================================
    op.add_column(
        "notifications",
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "action_buttons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "category",
            sa.Text(),
            nullable=True,
        ),  # deadline, opportunity, celebration, inactivity
    )


def downgrade() -> None:
    # Drop new columns from notifications
    op.drop_column("notifications", "category")
    op.drop_column("notifications", "action_buttons")
    op.drop_column("notifications", "expires_at")

    # Drop new columns from action_items
    op.drop_column("action_items", "last_reminder_sent")
    op.drop_column("action_items", "reminder_sent_count")
    op.drop_column("action_items", "advisor_persona")

    # Drop new columns from user_preferences
    op.drop_column("user_preferences", "push_subscription")
    op.drop_column("user_preferences", "location")

    # Drop user_activity_tracking table
    op.drop_table("user_activity_tracking")

    # Drop discovered_opportunities table
    op.drop_index("idx_opportunities_user_status", table_name="discovered_opportunities")
    op.drop_index("idx_opportunities_type", table_name="discovered_opportunities")
    op.drop_index("idx_opportunities_status", table_name="discovered_opportunities")
    op.drop_index("idx_opportunities_user", table_name="discovered_opportunities")
    op.drop_table("discovered_opportunities")
