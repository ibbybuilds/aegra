"""CRM API client for customer lookup during email validation.

This module provides customer lookup functionality to check if an email
belongs to an existing customer (repeat customer) before running paid
IPQS validation. This is Tier 2 of the email validation flow.

Authentication uses JWT tokens signed with a shared secret.
"""

import logging
import os
import time
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

# CRM endpoints by environment
CRM_ENDPOINTS = {
    "LOCAL": "https://crm-git-dev-etc-incubator.vercel.app",
    "DEVELOPMENT": "https://crm-git-dev-etc-incubator.vercel.app",
    "STAGING": "https://crm-git-dev-etc-incubator.vercel.app",  # Uses DEV CRM (same data)
    "PRODUCTION": "https://crm-self-alpha.vercel.app",
}

# Vercel protection bypass token (required for all environments)
VERCEL_BYPASS_TOKEN = "0O9Akk5jsYwb92UQswBAxLgnJmkYATIp"

# Default site ID for Reservations Portal
DEFAULT_SITE_ID = 3
DEFAULT_ISSUER = "reservations-portal"


def _get_crm_config() -> dict[str, Any]:
    """Get CRM configuration from environment variables.

    Returns:
        Dict with base_url, jwt_secret, site_id, issuer, timeout
    """
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()

    # Allow explicit override of CRM base URL
    base_url = os.getenv("CRM_BASE_URL") or CRM_ENDPOINTS.get(env_mode, CRM_ENDPOINTS["LOCAL"])

    config = {
        "base_url": base_url,
        "jwt_secret": os.getenv("CRM_JWT_SECRET"),
        "site_id": int(os.getenv("CRM_SITE_ID", str(DEFAULT_SITE_ID))),
        "issuer": os.getenv("CRM_ISSUER", DEFAULT_ISSUER),
        "timeout": float(os.getenv("CRM_TIMEOUT", "10.0")),
        "enabled": os.getenv("CRM_LOOKUP_ENABLED", "true").lower() == "true",
    }

    return config


def _generate_crm_token(config: dict[str, Any]) -> str:
    """Generate a JWT token for CRM API authentication.

    Args:
        config: CRM configuration dict with jwt_secret, site_id, issuer

    Returns:
        JWT token string

    Raises:
        ValueError: If jwt_secret is not configured
    """
    if not config["jwt_secret"]:
        raise ValueError("CRM_JWT_SECRET environment variable is required")

    now = int(time.time())
    expires_in = 3600  # 1 hour

    payload = {
        "siteId": config["site_id"],
        "iss": config["issuer"],
        "iat": now,
        "exp": now + expires_in,
    }

    token = jwt.encode(payload, config["jwt_secret"], algorithm="HS256")
    return token


async def check_existing_customer(email: str) -> bool:
    """Check if email belongs to an existing customer in CRM.

    This is Tier 2 of the email validation flow. If the customer exists
    in the CRM (has previous bookings), we skip the paid IPQS check.

    Args:
        email: Email address to check

    Returns:
        True if customer exists (repeat customer), False if new customer
        Also returns False on any error (fail-open behavior)
    """
    config = _get_crm_config()

    # Skip if CRM lookup is disabled
    if not config["enabled"]:
        logger.debug("[CRM_CLIENT] CRM lookup disabled, treating as new customer")
        return False

    # Skip if JWT secret not configured
    if not config["jwt_secret"]:
        logger.warning("[CRM_CLIENT] CRM_JWT_SECRET not configured, skipping CRM lookup")
        return False

    # Normalize email to lowercase for consistent matching
    email = email.strip().lower()
    domain = email.split('@')[-1]

    logger.info(f"[CRM_CLIENT] Querying CRM with full email (showing domain for privacy): {domain}")

    try:
        # Generate JWT token
        token = _generate_crm_token(config)

        # Build request
        url = f"{config['base_url']}/api/crm/customers/search"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-vercel-protection-bypass": VERCEL_BYPASS_TOKEN,
        }
        body = {
            "q": email,
            "dateRange": "all",
        }

        # Make request
        async with httpx.AsyncClient(timeout=config["timeout"]) as client:
            response = await client.post(url, headers=headers, json=body)

            # Handle 400 (query too short) - shouldn't happen with valid email
            if response.status_code == 400:
                logger.warning(f"[CRM_CLIENT] Bad request (400): {response.text}")
                return False

            response.raise_for_status()
            data = response.json()

            # Response is an array of customer objects
            # Empty array = no customer found
            # Non-empty array = customer exists
            customer_exists = len(data) > 0

            if customer_exists:
                # Log minimal info for debugging (no PII)
                customer_count = len(data)
                has_bookings = any(len(c.get("bookings", [])) > 0 for c in data)
                logger.info(
                    f"[CRM_CLIENT] Customer EXISTS - "
                    f"matches={customer_count}, has_bookings={has_bookings}"
                )
            else:
                logger.info("[CRM_CLIENT] Customer NOT FOUND - new customer")

            return customer_exists

    except httpx.TimeoutException:
        logger.warning(
            f"[CRM_CLIENT] Timeout after {config['timeout']}s, treating as new customer"
        )
        return False

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[CRM_CLIENT] HTTP error {e.response.status_code}: {e}, treating as new customer"
        )
        return False

    except ValueError as e:
        # JWT secret not configured
        logger.warning(f"[CRM_CLIENT] Configuration error: {e}, treating as new customer")
        return False

    except Exception as e:
        logger.error(f"[CRM_CLIENT] Unexpected error: {e}, treating as new customer")
        return False


__all__ = [
    "check_existing_customer",
    "_get_crm_config",
    "_generate_crm_token",
]
