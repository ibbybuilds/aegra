"""Google Model Armor API client for content policy enforcement."""

import logging
import os
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class ModelArmorConfigError(Exception):
    """Raised when Model Armor configuration is invalid or API unavailable."""

    pass


class ModelArmorViolationError(Exception):
    """Raised when content violates Model Armor policy.

    Attributes:
        message: Human-readable error message
        filter_results: Raw filter results from API (for logging/analysis)
    """

    def __init__(self, message: str, filter_results: dict[str, Any]):
        super().__init__(message)
        self.filter_results = filter_results


def _is_model_armor_enabled() -> bool:
    """Determine if Model Armor should be enabled.

    Enabled if:
    1. MODEL_ARMOR_ENABLED=true, OR
    2. ENV_MODE=PRODUCTION (auto-enable in production)

    Disabled if:
    3. MODEL_ARMOR_ENABLED=false, OR
    4. ENV_MODE in ['LOCAL', 'DEVELOPMENT']
    """
    explicit = os.getenv("MODEL_ARMOR_ENABLED", "").lower()
    if explicit in ["true", "false"]:
        return explicit == "true"

    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    return env_mode == "PRODUCTION"


def _get_model_armor_config() -> dict[str, Any]:
    """Get Model Armor configuration from environment variables.

    Returns:
        Dict with project_id, location, template_id, service_account_path,
        service_account_json, timeout, log_violations, fail_open

    Raises:
        ModelArmorConfigError: If configuration is invalid or incomplete
    """
    enabled = _is_model_armor_enabled()

    config = {
        "enabled": enabled,
        "project_id": os.getenv("MODEL_ARMOR_PROJECT_ID"),
        "location": os.getenv("MODEL_ARMOR_LOCATION"),
        "template_id": os.getenv("MODEL_ARMOR_TEMPLATE_ID"),
        "service_account_path": os.getenv("MODEL_ARMOR_SERVICE_ACCOUNT_PATH"),
        "service_account_json": os.getenv("MODEL_ARMOR_SERVICE_ACCOUNT_JSON"),
        "timeout": float(os.getenv("MODEL_ARMOR_TIMEOUT", "5.0")),
        "log_violations": os.getenv("MODEL_ARMOR_LOG_VIOLATIONS", "true").lower()
        == "true",
        "fail_open": os.getenv("MODEL_ARMOR_FAIL_OPEN", "false").lower() == "true",
    }

    # Validate required fields when enabled
    if enabled:
        missing_fields = []
        for field in ["project_id", "location", "template_id"]:
            if not config[field]:
                missing_fields.append(f"MODEL_ARMOR_{field.upper()}")

        if missing_fields:
            raise ModelArmorConfigError(
                f"Model Armor is enabled but missing required configuration: {', '.join(missing_fields)}"
            )

        # Validate authentication method
        # Option 1: Service account JSON file path
        # Option 2: Service account JSON in environment variable
        # Option 3: Application Default Credentials (gcloud CLI)
        sa_path = config["service_account_path"]
        sa_json = config["service_account_json"]

        if sa_path and not os.path.isfile(sa_path):
            raise ModelArmorConfigError(
                f"Model Armor service account file not found: {sa_path}"
            )

        # If both path and JSON are provided, prefer path
        if sa_path and sa_json:
            logger.warning(
                "[MODEL_ARMOR] Both service_account_path and service_account_json provided. Using path."
            )

        # If neither is provided, will use Application Default Credentials
        if not sa_path and not sa_json:
            logger.info(
                "[MODEL_ARMOR] No service account credentials provided. Using Application Default Credentials (gcloud CLI)."
            )

        # Validate timeout
        if config["timeout"] <= 0 or config["timeout"] > 30:
            raise ModelArmorConfigError(
                f"MODEL_ARMOR_TIMEOUT must be between 0 and 30 seconds (got {config['timeout']})"
            )

    return config


def _get_access_token(config: dict[str, Any]) -> str:
    """Generate Google OAuth2 access token.

    Authentication methods (in order of precedence):
    1. Service account JSON file path (MODEL_ARMOR_SERVICE_ACCOUNT_PATH)
    2. Service account JSON in environment variable (MODEL_ARMOR_SERVICE_ACCOUNT_JSON)
    3. Application Default Credentials (gcloud CLI)

    Args:
        config: Model Armor configuration dict

    Returns:
        OAuth2 access token string

    Raises:
        ModelArmorConfigError: If token generation fails
    """
    import json

    from google.auth import default

    try:
        credentials = None
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]

        # Method 1: Service account file path
        if config.get("service_account_path"):
            logger.debug("[MODEL_ARMOR] Using service account file for authentication")
            credentials = service_account.Credentials.from_service_account_file(
                config["service_account_path"],
                scopes=scopes,
            )

        # Method 2: Service account JSON from environment variable
        elif config.get("service_account_json"):
            logger.debug(
                "[MODEL_ARMOR] Using service account JSON from environment variable"
            )
            try:
                # Parse JSON from environment variable
                sa_info = json.loads(config["service_account_json"])
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=scopes,
                )
            except json.JSONDecodeError as e:
                raise ModelArmorConfigError(
                    f"Invalid JSON in MODEL_ARMOR_SERVICE_ACCOUNT_JSON: {e}"
                ) from e

        # Method 3: Application Default Credentials (gcloud CLI)
        else:
            logger.debug(
                "[MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)"
            )
            credentials, project = default(scopes=scopes)

        # Refresh credentials to get token
        credentials.refresh(Request())

        if not credentials.token:
            raise ModelArmorConfigError(
                "Failed to generate access token: credentials.token is None"
            )

        return credentials.token

    except ModelArmorConfigError:
        # Re-raise our custom errors
        raise
    except Exception as e:
        raise ModelArmorConfigError(
            f"Failed to generate Model Armor access token: {e}"
        ) from e


def get_model_armor_client(config: dict[str, Any]) -> httpx.AsyncClient:
    """Create httpx.AsyncClient with Google OAuth2 authentication.

    Args:
        config: Model Armor configuration dict

    Returns:
        httpx.AsyncClient configured with Bearer token and base URL

    Raises:
        ModelArmorConfigError: If authentication fails

    Usage:
        config = _get_model_armor_config()
        async with get_model_armor_client(config) as client:
            response = await client.post("/path", json=data)
    """
    token = _get_access_token(config)

    base_url = (
        f"https://modelarmor.{config['location']}.rep.googleapis.com"
        f"/v1/projects/{config['project_id']}/locations/{config['location']}"
        f"/templates/{config['template_id']}"
    )

    return httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=config["timeout"],
    )


async def sanitize_user_prompt(text: str) -> None:
    """Check user prompt against Model Armor policy (pre-call sanitization).

    Args:
        text: User prompt text to check

    Raises:
        ModelArmorConfigError: If Model Armor is misconfigured or API unavailable
        ModelArmorViolationError: If content violates policy
    """
    config = _get_model_armor_config()

    if not config["enabled"]:
        logger.debug("[MODEL_ARMOR] Middleware disabled, skipping user prompt check")
        return

    logger.debug(f"[MODEL_ARMOR] Sanitizing user prompt (length={len(text)})")

    try:
        async with get_model_armor_client(config) as client:
            # Use full URL path to preserve the colon
            url = (
                f"https://modelarmor.{config['location']}.rep.googleapis.com"
                f"/v1/projects/{config['project_id']}/locations/{config['location']}"
                f"/templates/{config['template_id']}:sanitizeUserPrompt"
            )
            response = await client.post(
                url,
                json={"userPromptData": {"text": text}},
            )
            response.raise_for_status()
            data = response.json()

            # Check for violations
            # API returns: {"sanitizationResult": {"filterMatchState": "MATCH_FOUND|NO_MATCH_FOUND", "filterResults": {...}}}
            sanitization_result = data.get("sanitizationResult", {})
            filter_match_state = sanitization_result.get("filterMatchState", "")
            blocked = filter_match_state == "MATCH_FOUND"

            if blocked:
                filter_results = sanitization_result.get("filterResults", {})
                if config["log_violations"]:
                    logger.warning(
                        f"[MODEL_ARMOR] User prompt blocked: {filter_results}"
                    )

                raise ModelArmorViolationError(
                    "Content violates policy", filter_results=filter_results
                )

            logger.debug("[MODEL_ARMOR] User prompt passed sanitization")

    except ModelArmorViolationError:
        # Re-raise violations as-is
        raise
    except httpx.TimeoutException as e:
        error_msg = f"Model Armor API timeout after {config['timeout']}s: {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing request despite timeout"
        )
    except httpx.HTTPStatusError as e:
        error_msg = f"Model Armor API error (status {e.response.status_code}): {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing request despite API error"
        )
    except Exception as e:
        error_msg = f"Model Armor API unexpected error: {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing request despite error"
        )


async def sanitize_model_response(text: str) -> None:
    """Check model response against Model Armor policy (post-call sanitization).

    Args:
        text: Model response text to check

    Raises:
        ModelArmorConfigError: If Model Armor is misconfigured or API unavailable
        ModelArmorViolationError: If content violates policy
    """
    config = _get_model_armor_config()

    if not config["enabled"]:
        logger.debug("[MODEL_ARMOR] Middleware disabled, skipping response check")
        return

    logger.debug(f"[MODEL_ARMOR] Sanitizing model response (length={len(text)})")

    try:
        async with get_model_armor_client(config) as client:
            # Use full URL path to preserve the colon
            url = (
                f"https://modelarmor.{config['location']}.rep.googleapis.com"
                f"/v1/projects/{config['project_id']}/locations/{config['location']}"
                f"/templates/{config['template_id']}:sanitizeModelResponse"
            )
            response = await client.post(
                url,
                json={"modelResponseData": {"text": text}},
            )
            response.raise_for_status()
            data = response.json()

            # Check for violations
            # API returns: {"sanitizationResult": {"filterMatchState": "MATCH_FOUND|NO_MATCH_FOUND", "filterResults": {...}}}
            sanitization_result = data.get("sanitizationResult", {})
            filter_match_state = sanitization_result.get("filterMatchState", "")
            blocked = filter_match_state == "MATCH_FOUND"

            if blocked:
                filter_results = sanitization_result.get("filterResults", {})
                if config["log_violations"]:
                    logger.warning(
                        f"[MODEL_ARMOR] Model response blocked: {filter_results}"
                    )

                raise ModelArmorViolationError(
                    "Content violates policy", filter_results=filter_results
                )

            logger.debug("[MODEL_ARMOR] Model response passed sanitization")

    except ModelArmorViolationError:
        # Re-raise violations as-is
        raise
    except httpx.TimeoutException as e:
        error_msg = f"Model Armor API timeout after {config['timeout']}s: {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing response despite timeout"
        )
    except httpx.HTTPStatusError as e:
        error_msg = f"Model Armor API error (status {e.response.status_code}): {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing response despite API error"
        )
    except Exception as e:
        error_msg = f"Model Armor API unexpected error: {e}"
        logger.error(f"[MODEL_ARMOR] {error_msg}")

        if not config["fail_open"]:
            raise ModelArmorConfigError(error_msg) from e

        logger.warning(
            "[MODEL_ARMOR] Fail-open mode: allowing response despite error"
        )


__all__ = [
    "ModelArmorConfigError",
    "ModelArmorViolationError",
    "_is_model_armor_enabled",
    "_get_model_armor_config",
    "get_model_armor_client",
    "sanitize_user_prompt",
    "sanitize_model_response",
]
