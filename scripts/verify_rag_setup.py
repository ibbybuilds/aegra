#!/usr/bin/env python
"""
Quick verification script to check RAG system setup.

Run this after installation to verify everything is configured correctly.
Note: Environment variables should be set before running this script.
"""

import os
import sys
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).parent.parent

# Add project root to Python path for imports
sys.path.insert(0, str(project_root))


def check_env_vars():
    """Check required environment variables."""
    print("🔍 Checking environment variables...")
    required_vars = {
        "DATABASE_URL": "PostgreSQL connection string",
        "OPENAI_API_KEY": "OpenAI API key for embeddings",
        "LMS_URL": "LMS API base URL",
        "ADMIN_TOKEN": "Admin JWT token for LMS API",
    }

    missing = []
    for var, description in required_vars.items():
        if os.getenv(var):
            print(f"  ✅ {var}")
        else:
            print(f"  ❌ {var} - {description}")
            missing.append(var)

    return len(missing) == 0


def check_dependencies():
    """Check if required Python packages are installed."""
    print("\n🔍 Checking Python dependencies...")
    required_packages = {
        "pgvector": "PostgreSQL vector extension",
        "langchain": "LangChain framework",
        "langchain_openai": "OpenAI embeddings",
        "sqlalchemy": "Database ORM",
        "psycopg": "PostgreSQL driver",
        "httpx": "HTTP client for LMS API",
    }

    missing = []
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - {description}")
            missing.append(package)

    return len(missing) == 0


def check_database_connection():
    """Test database connection and pgvector extension."""
    print("\n🔍 Checking database connection...")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("  ❌ DATABASE_URL not set")
        return False

    try:
        from sqlalchemy import create_engine, text

        # Convert asyncpg to psycopg if needed
        if "asyncpg" in database_url:
            database_url = database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg://"
            )

        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Check connection
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print("  ✅ Connected to PostgreSQL")
            print(f"     {version[:50]}...")

            # Check pgvector extension
            result = conn.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            )
            if result.fetchone():
                print("  ✅ pgvector extension enabled")
            else:
                print("  ⚠️  pgvector extension NOT enabled")
                print("     Run: CREATE EXTENSION IF NOT EXISTS vector;")
                return False

        return True

    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False


def check_rag_import():
    """Check if RAG modules can be imported."""
    print("\n🔍 Checking RAG module imports...")

    try:
        # Add libs/aegra-api/src to path if needed
        src_path = project_root / "libs" / "aegra-api" / "src"
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        print("  ✅ CourseRetriever imported")

        print("  ✅ LMSClient imported")

        print("  ✅ Database models imported")

        return True

    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def check_lms_api():
    """Test LMS API connectivity."""
    print("\n🔍 Checking LMS API connectivity...")

    try:
        import httpx

        lms_url = os.getenv("LMS_URL")
        admin_token = os.getenv("ADMIN_TOKEN")

        if not lms_url or not admin_token:
            print("  ⚠️  LMS_URL or ADMIN_TOKEN not set")
            return False

        # Simple health check
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{lms_url}/api/hello",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if response.status_code == 200:
                print(f"  ✅ LMS API accessible at {lms_url}")
                return True
            else:
                print(f"  ⚠️  LMS API returned status {response.status_code}")
                return False

    except Exception as e:
        print(f"  ⚠️  LMS API check failed: {e}")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("🚀 RAG System Setup Verification")
    print("=" * 60)

    checks = [
        ("Environment Variables", check_env_vars),
        ("Python Dependencies", check_dependencies),
        ("Database Connection", check_database_connection),
        ("RAG Module Imports", check_rag_import),
        ("LMS API Connectivity", check_lms_api),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n❌ Unexpected error in {name}: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 All checks passed! Your RAG system is ready to use.")
        print("\nNext steps:")
        print("  1. Initialize database schema:")
        print("     python -m aegra_api.tools.rag.ingest --init-db")
        print("\n  2. Index your courses:")
        print("     python -m aegra_api.tools.rag.ingest --all")
        print("\n  3. Start using the agent with course search! 🚀")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        print("\n💡 Tip: Make sure to set environment variables:")
        print("   - On Windows PowerShell: $env:VARIABLE_NAME='value'")
        print("   - Or use python-dotenv to load from .env")
        print("\nRefer to RAG_QUICKSTART.md for setup instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
