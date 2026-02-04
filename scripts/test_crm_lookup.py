#!/usr/bin/env python3
"""Quick test script for CRM customer lookup integration.

Usage:
    uv run python scripts/test_crm_lookup.py <email>

Examples:
    uv run python scripts/test_crm_lookup.py test@gmail.com
    uv run python scripts/test_crm_lookup.py customer@example.com
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_crm_lookup(email: str) -> None:
    """Test CRM customer lookup for a given email."""
    # Import after dotenv load
    from ava_v1.shared_libraries.crm_client import (
        _get_crm_config,
        check_existing_customer,
    )

    print("=" * 60)
    print("CRM Customer Lookup Test")
    print("=" * 60)

    # Show configuration (without secrets)
    config = _get_crm_config()
    print(f"\nConfiguration:")
    print(f"  Base URL: {config['base_url']}")
    print(f"  Site ID: {config['site_id']}")
    print(f"  Issuer: {config['issuer']}")
    print(f"  Timeout: {config['timeout']}s")
    print(f"  Enabled: {config['enabled']}")
    print(f"  JWT Secret configured: {'Yes' if config['jwt_secret'] else 'No'}")

    if not config["jwt_secret"]:
        print("\n❌ ERROR: CRM_JWT_SECRET not configured in .env")
        print("Add: CRM_JWT_SECRET=<your-secret>")
        return

    if not config["enabled"]:
        print("\n⚠️  WARNING: CRM lookup is disabled (CRM_LOOKUP_ENABLED=false)")
        return

    print(f"\nTesting email: {email}")
    print("-" * 40)

    try:
        is_repeat = await check_existing_customer(email)

        if is_repeat:
            print(f"\n✅ RESULT: Customer EXISTS (repeat customer)")
            print("   → Would SKIP IPQS validation")
        else:
            print(f"\n✅ RESULT: Customer NOT FOUND (new customer)")
            print("   → Would proceed to IPQS validation")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")


async def test_full_email_validation(email: str) -> None:
    """Test full email validation flow including CRM lookup."""
    from ava_v1.shared_libraries.email_validator import check_email_validity

    print("\n" + "=" * 60)
    print("Full Email Validation Test (All Tiers)")
    print("=" * 60)
    print(f"\nTesting email: {email}")
    print("-" * 40)

    is_valid, error_hint = await check_email_validity(email)

    if is_valid:
        print(f"\n✅ RESULT: Email ACCEPTED")
    else:
        print(f"\n❌ RESULT: Email REJECTED")
        print(f"   Error: {error_hint}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/test_crm_lookup.py <email>")
        print("\nExamples:")
        print("  uv run python scripts/test_crm_lookup.py test@gmail.com")
        print("  uv run python scripts/test_crm_lookup.py customer@example.com")
        sys.exit(1)

    email = sys.argv[1]

    # Run tests
    asyncio.run(test_crm_lookup(email))
    asyncio.run(test_full_email_validation(email))
