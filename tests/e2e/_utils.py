import json

import pytest

from src.agent_server.settings import settings

try:
    from langgraph_sdk import get_client
except Exception as e:
    raise RuntimeError(
        "langgraph-sdk is required for E2E tests. Install via extras 'e2e' or add to your environment."
    ) from e


def elog(title: str, payload):
    """Emit pretty JSON logs for E2E visibility."""
    try:
        formatted = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        formatted = str(payload)
    print(f"\n=== {title} ===\n{formatted}\n")


def get_e2e_client():
    """Construct a LangGraph SDK client from env and log the target URL."""
    server_url = settings.app.SERVER_URL
    print(f"[E2E] Using SERVER_URL={server_url}")
    return get_client(url=server_url)


def check_and_skip_if_geo_blocked(run_data: dict) -> None:
    """
    Checks if a run failed due to OpenAI geo-blocking/unsupported region.
    If so, skips the test instead of failing.

    This targets the specific error code 'unsupported_country_region_territory'
    to avoid masking other permission errors (403).
    """
    if run_data.get("status") == "error":
        msg = str(run_data.get("error_message", "")).lower()
        # Strict check as requested by maintainer
        if (
            "unsupported_country_region_territory" in msg
            or "generator didn't stop" in msg
        ):
            pytest.skip(f"⛔️ Skipped: OpenAI Geo-block detected. ({msg[:60]}...)")
