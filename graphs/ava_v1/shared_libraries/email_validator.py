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
import os
import time
import urllib.parse
from pathlib import Path
from typing import Tuple

import dns.resolver
import httpx

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

        # Check for null MX record (0 .) which means "no email accepted"
        # Null MX has priority 0 and exchange "."
        for mx in mx_records:
            if mx.preference == 0 and str(mx.exchange) == ".":
                logger.info(f"[EMAIL_VALIDATOR] Null MX record (no email) for domain: {domain}")
                return False

        logger.debug(f"[EMAIL_VALIDATOR] Valid MX records found for domain: {domain}")
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


async def validate_email_with_ipqs(email: str) -> dict | None:
    """Call IPQualityScore API to validate email.

    API Documentation: https://www.ipqualityscore.com/documentation/email-validation-api/overview

    NOTE: This function is for evaluation/testing only. Not yet integrated
    into the main validation flow.

    Args:
        email: Email address to validate

    Returns:
        Dict with IPQS response data and timing info, or None if API unavailable
        Response includes all IPQS fields plus:
        - _latency_ms: Request latency in milliseconds
        - _error: Error message if request failed

    Key IPQS response fields:
        - valid (bool): Email appears structurally and functionally valid
        - fraud_score (float): 0-100, scores ≥75 warrant suspension, ≥90 high risk
        - smtp_score (int): -1=invalid, 0=rejects all, 1=temp error, 2=catch-all, 3=verified exists
        - overall_score (int): 0-4, higher is better (4=verified exists)
        - disposable (bool): Temporary/disposable email service
        - catch_all (bool): Server accepts all emails (less reliable verification)
        - honeypot (bool): Suspected spam trap
        - recent_abuse (bool): Recently verified abusive activity
        - suggested_domain (str): Typo correction suggestion (e.g., "gmail.com" for "gmial.com")
        - deliverability (str): "high", "medium", or "low"
        - domain_trust (str): "trusted", "positive", "neutral", "suspicious", "malicious"
    """
    api_key = os.getenv("IPQUALITYSCORE_API_KEY")
    if not api_key:
        logger.warning("[IPQS] API key not configured")
        return None

    # URL-encode email for API call
    encoded_email = urllib.parse.quote(email, safe="")
    url = f"https://www.ipqualityscore.com/api/json/email/{api_key}/{encoded_email}"

    # Parameters for full SMTP validation
    # See: https://www.ipqualityscore.com/documentation/email-validation-api/overview
    params = {
        "timeout": 20,  # 1-60 seconds, default 7. Higher = more accurate SMTP checks
        "fast": "false",  # Full validation, not fast mode
        "abuse_strictness": 0,  # 0-2, higher = more false positives
    }

    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            latency_ms = (time.perf_counter() - start_time) * 1000

            response.raise_for_status()
            data = response.json()

            # Check for API-level errors
            if not data.get("success", True):
                errors = data.get("errors", [])
                logger.error(f"[IPQS] API error for {email.split('@')[-1]}: {errors}")
                return {"_error": f"api_error: {errors}", "_latency_ms": round(latency_ms, 2)}

            # Add timing info
            data["_latency_ms"] = round(latency_ms, 2)

            logger.info(
                f"[IPQS] Response for {email.split('@')[-1]}: "
                f"fraud_score={data.get('fraud_score')}, "
                f"smtp_score={data.get('smtp_score')}, "
                f"overall_score={data.get('overall_score')}, "
                f"valid={data.get('valid')}, "
                f"disposable={data.get('disposable')}, "
                f"catch_all={data.get('catch_all')}, "
                f"honeypot={data.get('honeypot')}, "
                f"domain_trust={data.get('domain_trust')}, "
                f"suggested_domain={data.get('suggested_domain')}, "
                f"latency={latency_ms:.0f}ms"
            )

            return data

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(f"[IPQS] Timeout after {latency_ms:.0f}ms for {email.split('@')[-1]}")
        return {"_error": "timeout", "_latency_ms": round(latency_ms, 2)}

    except httpx.HTTPStatusError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"[IPQS] HTTP {e.response.status_code} for {email.split('@')[-1]}")
        return {"_error": f"http_{e.response.status_code}", "_latency_ms": round(latency_ms, 2)}

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"[IPQS] Error for {email.split('@')[-1]}: {e}")
        return {"_error": str(e), "_latency_ms": round(latency_ms, 2)}


def interpret_ipqs_result(data: dict) -> Tuple[bool, str | None, dict]:
    """Interpret IPQS response and return validation result.

    Based on IPQS documentation:
    https://www.ipqualityscore.com/documentation/email-validation-api/response-parameters

    Optimized for hotel booking use case - focuses on hard signals that indicate
    the email is fake/invalid, NOT soft signals like leaked credentials or
    frequent complainer status (which affect fraud_score but aren't relevant
    for legitimate bookings).

    Args:
        data: IPQS API response dict

    Returns:
        Tuple of (is_valid, rejection_reason, details)
        - is_valid: True if email passes all checks
        - rejection_reason: Human-readable reason if rejected, None if valid
        - details: Dict with additional context for evaluation
    """
    details = {
        "fraud_score": data.get("fraud_score"),
        "smtp_score": data.get("smtp_score"),
        "overall_score": data.get("overall_score"),
        "spam_trap_score": data.get("spam_trap_score"),
        "deliverability": data.get("deliverability"),
        "leaked": data.get("leaked"),
        "frequent_complainer": data.get("frequent_complainer"),
    }

    if "_error" in data:
        return (True, None, {"_error": data["_error"]})  # Fail open on API errors

    # ==========================================================================
    # HARD REJECT CRITERIA - These indicate the email is definitively bad
    # ==========================================================================

    # 1. Honeypot - Known spam trap, definite reject
    if data.get("honeypot", False):
        return (False, "This email cannot be verified for booking purposes. Ask the user to provide a different email address.", details)

    # 2. Disposable/temporary email - Won't be reachable long-term
    if data.get("disposable", False):
        return (False, "The email is from a temporary/disposable service. Ask the user for a permanent email address they check regularly.", details)

    # 3. SMTP score - Does the email actually exist?
    # -1 = invalid, 0 = server rejects all mail, 1 = temp error, 2 = catch-all, 3 = verified
    smtp_score = data.get("smtp_score")
    if smtp_score == -1:
        suggested = data.get("suggested_domain")
        if suggested and suggested != "N/A":
            return (False, f"The email does not exist. The domain appears to be a typo - suggest @{suggested} to the user.", details)
        return (False, "The email address does not exist at this domain. Ask the user to double-check the spelling or provide a different email.", details)
    if smtp_score == 0:
        return (False, "This email domain does not accept incoming emails. Ask the user to provide a different email address.", details)

    # 4. Valid flag - Basic structural validity
    if not data.get("valid", True):
        return (False, "The email address could not be validated. Ask the user to verify the spelling or provide a different email.", details)

    # 5. High spam trap score - High confidence this is a trap
    spam_trap_score = data.get("spam_trap_score", "none")
    if spam_trap_score == "high":
        return (False, "This email cannot be verified for booking purposes. Ask the user to provide a different email address.", details)

    # 6. Recent abuse - Known bad actor (chargebacks, fake signups, etc.)
    if data.get("recent_abuse", False):
        return (False, "This email cannot be verified for booking purposes. Ask the user to provide a different email address.", details)

    # ==========================================================================
    # PASS - Email is valid for booking purposes
    # ==========================================================================

    # Add informational warnings (don't reject, just note)
    warnings = []
    if data.get("catch_all", False):
        warnings.append("catch_all domain")
    if smtp_score == 1:
        warnings.append("smtp temporary error")
    if data.get("deliverability") == "low":
        warnings.append("low deliverability")
    if data.get("leaked", False):
        warnings.append("appeared in data breach")
    if data.get("frequent_complainer", False):
        warnings.append("frequent spam complainer")

    if warnings:
        details["warnings"] = warnings

    return (True, None, details)


async def check_email_validity(email: str) -> Tuple[bool, str | None]:
    """Validate email using tiered approach for cost optimization.

    Tier 1 - FREE checks (always run):
        1. Syntax validation
        2. Disposable domain blocklist
        3. Trusted provider whitelist → ACCEPT, skip IPQS
        4. MX record validation

    Tier 2 - IPQS API (only for unknown domains that pass Tier 1):
        - Checks: honeypot, disposable, smtp_score, valid, spam_trap_score, recent_abuse
        - Does NOT use fraud_score (too many false positives)
        - If API fails → ACCEPT (free checks already passed)

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_hint):
        - is_valid: True if email passes all checks
        - error_hint: User-friendly error message if invalid, None if valid
    """
    domain = email.split('@')[-1].lower() if '@' in email else 'invalid'
    logger.info(f"[EMAIL_VALIDATOR] Starting validation for domain: {domain}")

    # =========================================================================
    # TIER 1: FREE CHECKS
    # =========================================================================

    # Check 1: Syntax validation
    if not _validate_email(email):
        logger.info(f"[EMAIL_VALIDATOR] REJECTED - syntax_invalid, Domain: {domain}")
        return (False, "The email address has invalid syntax (missing @ or domain). Ask the user to spell out their complete email address again.")

    # Extract domain
    try:
        domain = email.split("@")[1].lower()
    except IndexError:
        logger.info(f"[EMAIL_VALIDATOR] REJECTED - domain_extraction_failed")
        return (False, "The email address has invalid syntax (missing @ or domain). Ask the user to spell out their complete email address again.")

    # Check 2: Disposable domain blocklist
    if is_disposable_domain(domain):
        logger.info(f"[EMAIL_VALIDATOR] REJECTED - disposable_domain, Domain: {domain}")
        return (
            False,
            "The email is from a temporary/disposable email service. Ask the user for a permanent email address they check regularly.",
        )

    # Check 3: Trusted provider whitelist (skip IPQS)
    if is_trusted_provider(domain):
        logger.info(f"[EMAIL_VALIDATOR] ACCEPTED - trusted_provider, Domain: {domain}, IPQS: skipped")
        return (True, None)

    # Check 4: MX record validation
    if not has_valid_mx_records(domain):
        logger.info(f"[EMAIL_VALIDATOR] REJECTED - no_mx_records, Domain: {domain}")
        return (
            False,
            "The email domain doesn't exist or can't receive emails (likely a typo). Ask the user to verify the spelling of their email address.",
        )

    # =========================================================================
    # TIER 2: IPQS API (only for unknown domains)
    # =========================================================================
    logger.info(f"[EMAIL_VALIDATOR] Tier 1 passed, calling IPQS for domain: {domain}")

    ipqs_response = await validate_email_with_ipqs(email)

    # If IPQS unavailable, accept (free checks passed)
    if ipqs_response is None:
        logger.info(f"[EMAIL_VALIDATOR] ACCEPTED - ipqs_not_configured, Domain: {domain}")
        return (True, None)

    # Interpret IPQS result (uses hard signals, not fraud_score)
    is_valid, rejection_reason, details = interpret_ipqs_result(ipqs_response)

    if is_valid:
        warnings = details.get("warnings", [])
        logger.info(
            f"[EMAIL_VALIDATOR] ACCEPTED - ipqs_passed, Domain: {domain}, "
            f"smtp={details.get('smtp_score')}, fraud={details.get('fraud_score')}"
            f"{f', warnings={warnings}' if warnings else ''}"
        )
        return (True, None)
    else:
        logger.info(
            f"[EMAIL_VALIDATOR] REJECTED - ipqs_failed, Domain: {domain}, "
            f"smtp={details.get('smtp_score')}, fraud={details.get('fraud_score')}, "
            f"reason={rejection_reason}"
        )
        return (False, rejection_reason)
