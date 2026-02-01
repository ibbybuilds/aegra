#!/usr/bin/env python3
"""Database migration management script for Aegra."""

import os
import subprocess
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_command(cmd: str, description: str = ""):
    """Run a command and handle errors."""
    if description:
        print(f"🔄 {description}")

    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running '{cmd}': {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False


def main():
    """Main migration management function."""
    if len(sys.argv) < 2:
        print("""
🔧 Aegra Database Migration Manager

Usage:
  python scripts/migrate.py <command> [options]

Commands:
  init          - Initialize Alembic (first time setup)
  upgrade       - Apply all pending migrations
  downgrade     - Rollback last migration
  revision      - Create a new migration file
  history       - Show migration history
  current       - Show current migration version
  reset         - Reset database (drop all tables and reapply migrations)

Examples:
  python scripts/migrate.py upgrade
  python scripts/migrate.py revision --autogenerate -m "Add user preferences"
  python scripts/migrate.py reset
        """)
        return

    command = sys.argv[1]

    # Change to project root directory
    os.chdir(project_root)

    if command == "init":
        print("🚀 Initializing Alembic...")
        if not run_command("alembic init alembic", "Creating Alembic directory"):
            return
        print("✅ Alembic initialized! You may need to update alembic.ini and env.py")

    elif command == "upgrade":
        if not run_command("alembic upgrade head", "Applying migrations"):
            return
        print("✅ All migrations applied successfully!")

    elif command == "downgrade":
        if not run_command("alembic downgrade -1", "Rolling back last migration"):
            return
        print("✅ Last migration rolled back!")

    elif command == "revision":
        # Pass through all arguments after 'revision', properly handling quotes
        if len(sys.argv) < 3:
            print("❌ Error: revision command requires a message")
            print('Usage: python scripts/migrate.py revision -m "Your message"')
            return

        # Use subprocess.run directly to avoid shell quoting issues
        try:
            cmd_parts = ["alembic", "revision"] + sys.argv[2:]
            result = subprocess.run(
                cmd_parts, check=True, capture_output=True, text=True
            )
            if result.stdout:
                print(result.stdout)
            print("✅ New migration created!")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running alembic revision: {e}")
            if e.stderr:
                print(f"Error output: {e.stderr}")
            return False

    elif command == "history":
        if not run_command("alembic history", "Showing migration history"):
            return

    elif command == "current":
        if not run_command("alembic current", "Showing current migration version"):
            return

    elif command == "reset":
        print("⚠️  WARNING: This will drop all tables and reapply migrations!")
        response = input("Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Reset cancelled")
            return

        print("🔄 Resetting database...")
        # Drop all tables (this is a simplified approach)
        if not run_command("alembic downgrade base", "Rolling back all migrations"):
            return
        if not run_command("alembic upgrade head", "Reapplying all migrations"):
            return
        print("✅ Database reset complete!")

    else:
        print(f"❌ Unknown command: {command}")
        print("Run 'python scripts/migrate.py' for help")


if __name__ == "__main__":
    main()
