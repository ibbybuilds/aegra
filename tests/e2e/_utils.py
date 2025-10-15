import json
import os

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
    server_url = os.getenv("SERVER_URL", "http://localhost:2024")
    print(f"[E2E] Using SERVER_URL={server_url}")
    return get_client(url=server_url)
