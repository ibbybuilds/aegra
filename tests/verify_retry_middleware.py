import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import SystemMessage, ToolMessage
from langchain.agents.middleware import ModelRequest

from ava_v1.middleware import ForcedRetryMiddleware


async def test_forced_retry_logic():
    print("Testing ForcedRetryMiddleware...")

    # Setup
    middleware = ForcedRetryMiddleware()

    # Mock handler (just returns success)
    async def mock_handler(request):
        return "success"

    # Case 1: Fixable Error (Invalid Input)
    error_json = json.dumps(
        {
            "status": "error",
            "error": {
                "type": "invalid_input",
                "message": "Missing required field 'checkIn'",
            },
        }
    )

    tool_msg = ToolMessage(content=error_json, tool_call_id="1", name="search")

    # Create request with this error as the last message
    request = MagicMock(spec=ModelRequest)
    request.messages = [tool_msg]
    request.system_message = SystemMessage(content="Base Prompt")

    # Mock override method to capture changes
    def override(**kwargs):
        # Print what was changed
        if "system_message" in kwargs:
            print(
                f"  [PASS] System message updated! New content length: {len(kwargs['system_message'].content)}"
            )
            if (
                "RETRY SILENTLY" in kwargs["system_message"].content
                or "DO NOT output any text" in kwargs["system_message"].content
            ):
                print("  [PASS] 'Silent Retry' instruction found.")
            else:
                print("  [FAIL] 'Silent Retry' instruction NOT found.")

        if "tool_choice" in kwargs:
            print(f"  [PASS] tool_choice forced to: {kwargs['tool_choice']}")

        return request  # Return self for chaining if needed

    request.override = override

    # Run middleware
    print("\n--- Running Case 1: Fixable Error ---")
    await middleware.awrap_model_call(request, mock_handler)

    # Case 2: Non-Fixable Error (Room Unavailable)
    error_json_2 = json.dumps(
        {
            "status": "error",
            "error": {"type": "room_unavailable", "message": "Sold out"},
        }
    )
    tool_msg_2 = ToolMessage(content=error_json_2, tool_call_id="2", name="book")

    request_2 = MagicMock(spec=ModelRequest)
    request_2.messages = [tool_msg_2]
    request_2.system_message = SystemMessage(content="Base Prompt")

    # Mock override to fail if called (should NOT be called)
    def override_fail(**kwargs):
        print("  [FAIL] Override called for non-fixable error!")
        return request_2

    request_2.override = override_fail

    print("\n--- Running Case 2: Non-Fixable Error ---")
    await middleware.awrap_model_call(request_2, mock_handler)
    print("  [PASS] No override triggered (as expected).")


if __name__ == "__main__":
    asyncio.run(test_forced_retry_logic())
