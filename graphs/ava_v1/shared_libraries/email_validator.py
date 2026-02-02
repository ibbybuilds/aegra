"""Email validation module with tiered approach (Tier 1: Free checks only).

This module provides cost-optimized email validation by running free checks first:
1. Syntax validation (regex)
2. Disposable domain blocklist check
3. MX record validation (DNS lookup)
4. Trusted provider whitelist (Gmail, Yahoo, etc.)

Future tiers (not yet implemented):
- Tier 2: CRM lookup for repeat customers
- Tier 3: IPQS API for unknown domains from first-time customers
"""

import logging
from pathlib import Path
from typing import Tuple

import dns.resolver

from ava_v1.shared_libraries.validation import _validate_email

logger = logging.getLogger(__name__)

# Tier 1: Trusted email providers (skip expensive checks)
TRUSTED_PROVIDERS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "aol.com",
    "live.com",
    "msn.com",
    "protonmail.com",
    "mail.com",
    "me.com",
    "yahoo.co.uk",
    "googlemail.com",
}

# Module-level cache for disposable domains (load once)
_DISPOSABLE_DOMAINS: set[str] | None = None


def _load_disposable_domains() -> set[str]:
    """Load disposable domain blocklist from file (cached in memory).

    Returns:
        Set of disposable email domains (lowercase)
    """
    global _DISPOSABLE_DOMAINS
    if _DISPOSABLE_DOMAINS is None:
        blocklist_path = Path(__file__).parent / "disposable_email_blocklist.txt"
        try:
            with open(blocklist_path, "r") as f:
                _DISPOSABLE_DOMAINS = {
                    line.strip().lower() for line in f if line.strip()
                }
            logger.info(
                f"[EMAIL_VALIDATOR] Loaded {len(_DISPOSABLE_DOMAINS)} disposable domains"
            )
        except FileNotFoundError:
            logger.error(
                f"[EMAIL_VALIDATOR] Disposable blocklist not found: {blocklist_path}"
            )
            _DISPOSABLE_DOMAINS = set()
    return _DISPOSABLE_DOMAINS


def is_disposable_domain(domain: str) -> bool:
    """Check if email domain is in disposable/temporary email blocklist.

    Args:
        domain: Email domain (e.g., "guerrillamail.com")

    Returns:
        True if domain is disposable, False otherwise
    """
    blocklist = _load_disposable_domains()
    return domain.lower() in blocklist


def has_valid_mx_records(domain: str) -> bool:
    """Check if domain has MX records (can receive email) via DNS lookup.

    Uses 5-second timeout to prevent blocking. Fails open (returns True)
    on DNS errors to avoid false rejections.

    Args:
        domain: Email domain to check (e.g., "gmail.com")

    Returns:
        True if domain has valid MX records or on DNS errors (fail open)
        False only if domain doesn't exist or has no MX records
    """
    try:
        # Set 5 second timeout for DNS query
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 5.0

        # Query MX records
        mx_records = resolver.resolve(domain, "MX")
        logger.debug(f"[EMAIL_VALIDATOR] MX records found for domain: {domain}")
        return len(mx_records) > 0

    except dns.resolver.NXDOMAIN:
        # Domain doesn't exist
        logger.info(f"[EMAIL_VALIDATOR] Domain does not exist: {domain}")
        return False

    except dns.resolver.NoAnswer:
        # No MX records found
        logger.info(f"[EMAIL_VALIDATOR] No MX records for domain: {domain}")
        return False

    except dns.exception.Timeout:
        # DNS timeout - fail open (assume valid to avoid false rejection)
        logger.warning(
            f"[EMAIL_VALIDATOR] DNS timeout for domain: {domain}, assuming valid"
        )
        return True

    except Exception as e:
        # Unexpected error - fail open
        logger.error(
            f"[EMAIL_VALIDATOR] DNS error for domain {domain}: {e}, assuming valid"
        )
        return True


def is_trusted_provider(domain: str) -> bool:
    """Check if domain is a major trusted email provider.

    Trusted providers skip expensive validation checks (MX, IPQS).

    Args:
        domain: Email domain (e.g., "gmail.com")

    Returns:
        True if domain is in trusted provider list
    """
    return domain.lower() in TRUSTED_PROVIDERS


async def check_email_validity(email: str) -> Tuple[bool, str | None]:
    """Validate email using Tier 1 free checks only.

    Runs checks in order, stopping at first rejection:
    1. Syntax validation (regex)
    2. Disposable domain check
    3. MX record validation
    4. Trusted provider check (accept if trusted)

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_hint):
        - is_valid: True if email passes all checks
        - error_hint: User-friendly error message if invalid, None if valid
    """
    # Tier 1 Check 1: Syntax validation
    if not _validate_email(email):
        logger.info(f"[EMAIL_VALIDATOR] Syntax validation failed")
        return (False, "Invalid email format")

    # Extract domain
    try:
        domain = email.split("@")[1].lower()
    except IndexError:
        logger.info(f"[EMAIL_VALIDATOR] Failed to extract domain from email")
        return (False, "Invalid email format")

    # Tier 1 Check 2: Disposable domain check
    if is_disposable_domain(domain):
        logger.info(f"[EMAIL_VALIDATOR] Disposable domain rejected: {domain}")
        return (
            False,
            "This appears to be a temporary/disposable email address. Please provide a permanent email address.",
        )

    # Tier 1 Check 3: Trusted provider whitelist (skip MX check if trusted)
    if is_trusted_provider(domain):
        logger.info(f"[EMAIL_VALIDATOR] Accepted trusted provider: {domain}")
        return (True, None)

    # Tier 1 Check 4: MX record validation
    if not has_valid_mx_records(domain):
        logger.info(f"[EMAIL_VALIDATOR] MX validation failed for domain: {domain}")
        return (
            False,
            "This email domain doesn't have valid mail servers. Please verify the spelling or provide a different email.",
        )

    # All Tier 1 checks passed
    logger.info(f"[EMAIL_VALIDATOR] Email validated successfully (Tier 1): {domain}")
    return (True, None)
