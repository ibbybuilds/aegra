"""Switch assistant/runs PK defaults from uuid-ossp to gen_random_uuid

The original ``7b79bfd12626`` migration created the ``uuid-ossp`` extension
and used ``public.uuid_generate_v4()::text`` as the server default for the
``assistant.assistant_id`` and ``runs.run_id`` primary keys. ``gen_random_uuid()``
ships with Postgres 13+ core, so the extension is no longer required.

Managed services such as Azure Database for PostgreSQL restrict the
allowed extension list and reject ``uuid-ossp``, which blocks the initial
migration from running. Switching to the core function unblocks those
deployments without changing behavior — both functions produce random v4
UUIDs.

Existing deployments already have the extension installed and tables seeded
with the old default. This migration only swaps the column default so new
inserts use the core function. The extension is left in place — dropping
it is risky if other applications on the same database use it, and harmless
otherwise.

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
    # uuid-ossp may not exist on every deployment we downgrade against.
    # Re-create it idempotently so the restored defaults remain callable.
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("ALTER TABLE assistant ALTER COLUMN assistant_id SET DEFAULT public.uuid_generate_v4()::text")
    op.execute("ALTER TABLE runs ALTER COLUMN run_id SET DEFAULT public.uuid_generate_v4()::text")
