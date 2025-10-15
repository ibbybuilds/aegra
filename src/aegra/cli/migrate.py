"""Database migration management script for Aegra."""

import os
from importlib import resources as ir

import click
from alembic import command
from alembic.config import Config


def load_alembic_config():
    dir = ir.files("aegra.cli")
    config = Config(str(dir.joinpath("alembic.ini")))
    config.set_main_option("script_location", str(dir.joinpath("alembic")))

    if "DATABASE_URL" not in os.environ:
        raise ValueError("DATABASE_URL environment variable is not set")

    config.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL"),
    )
    return config


@click.group()
def migrate():
    """Aegra Database Migration Manager"""
    pass


@migrate.command()
def init():
    """Initialize Alembic (first time setup)"""
    click.echo("🚀 Initializing Alembic...")
    command.init(
        load_alembic_config(),
        directory=str(ir.files("aegra.cli").joinpath("alembic")),
    )
    click.echo("✅ Alembic initialized! You may need to update alembic.ini and env.py")


@migrate.command()
def upgrade():
    """Apply all pending migrations"""
    click.echo("Applying migrations...")
    command.upgrade(load_alembic_config(), "head")
    click.echo("✅ All migrations applied successfully!")


@migrate.command()
@click.argument("message")
def revision(message):
    """Create a new migration file"""
    command.revision(load_alembic_config(), message)
    click.echo("✅ New migration created!")


@migrate.command()
def downgrade():
    """Rollback last migration"""
    click.echo("Rolling back last migration")
    command.downgrade(load_alembic_config(), "-1")
    click.echo("✅ Last migration rolled back!")


@migrate.command()
def history():
    """Show migration history"""
    click.echo("Showing migration history")
    command.history(load_alembic_config())


@migrate.command()
def current():
    """Show current migration version"""
    click.echo("Showing current migration version")
    command.current(load_alembic_config())


@migrate.command()
def reset():
    """Reset database (drop all tables and reapply migrations)"""
    if click.confirm("⚠️  WARNING: This will drop all tables and reapply migrations!"):
        click.echo("🔄 Resetting database...")
        # Drop all tables (this is a simplified approach)
        click.echo("Running back all migrations")
        command.downgrade(load_alembic_config(), "base")
        click.echo("Reapplying all migrations")
        command.upgrade(load_alembic_config(), "head")
        click.echo("✅ Database reset complete!")
