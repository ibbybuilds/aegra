"""Switch assistant/runs PK defaults from uuid-ossp to gen_random_uuid

gen_random_uuid() ships in Postgres 13+ core, so uuid-ossp is no longer
required. Managed services that restrict the extension allowlist (e.g.
Azure) reject CREATE EXTENSION uuid-ossp, blocking the initial migration.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a234b567
Create Date: 2026-05-12 00:00:00.000000

"""

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a234b567"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE assistant ALTER COLUMN assistant_id SET DEFAULT gen_random_uuid()::text")
    op.execute("ALTER TABLE runs ALTER COLUMN run_id SET DEFAULT gen_random_uuid()::text")


def downgrade() -> None:
    # Schema-only rollback. uuid-ossp is operator-managed: if the
    # restored default needs it and it's missing, install it out-of-band.
    op.execute("ALTER TABLE assistant ALTER COLUMN assistant_id SET DEFAULT public.uuid_generate_v4()::text")
    op.execute("ALTER TABLE runs ALTER COLUMN run_id SET DEFAULT public.uuid_generate_v4()::text")
