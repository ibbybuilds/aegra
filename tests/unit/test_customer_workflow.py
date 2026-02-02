import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

# Mock pytest decorator if not available
try:
    import pytest
except ImportError:
    class pytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ava_v1.state import AvaV1State, merge_dicts
from ava_v1.tools.book.update_customer import update_customer_details
from ava_v1.tools.book.book_room import book_room

# 1. Test State Schema Reducer
def test_merge_dicts_reducer():
    """Verify that merge_dicts correctly merges customer details."""
    print("Testing merge_dicts_reducer...")
    left = {"first_name": "John"}
    right = {"last_name": "Doe"}
    result = merge_dicts(left, right)
    assert result == {"first_name": "John", "last_name": "Doe"}

    # Verify overwrite precedence
    right_override = {"first_name": "Johnny"}
    result_2 = merge_dicts(result, right_override)
    assert result_2 == {"first_name": "Johnny", "last_name": "Doe"}
    print("  [PASS]")

# 2. Test update_customer_details tool
async def test_update_customer_details():
    """Verify the tool returns correct state update Command."""
    print("Testing update_customer_details tool...")

    # Mock runtime
    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call_123"

    # Access the underlying coroutine (it's async now)
    tool_coro = update_customer_details.coroutine

    # Test valid first_name update
    result = await tool_coro(
        field="first_name",
        value="Jane",
        runtime=mock_runtime
    )

    assert isinstance(result, Command)
    assert "customer_details" in result.update
    assert result.update["customer_details"] == {"first_name": "Jane"}

    # Test email validation failure (invalid syntax)
    result_invalid = await tool_coro(
        field="email",
        value="invalid-email",
        runtime=mock_runtime
    )
    # Should return JSON string error, not Command
    assert isinstance(result_invalid, str)
    assert "Invalid email format" in result_invalid
    print("  [PASS]")

# 3. Test book_room tool logic
async def test_book_room_state_dependency():
    """Verify book_room reads from state and validates presence."""
    print("Testing book_room state dependency...")
    
    # Access underlying coroutine
    tool_coro = book_room.coroutine
    
    # Mock runtime with empty state
    mock_runtime_empty = MagicMock()
    mock_runtime_empty.tool_call_id = "call_fail"
    mock_runtime_empty.state = {}
    mock_runtime_empty.context = None # Ensure we rely on state
    
    room_data = {
        "hotel_id": "123",
        "rate_key": "rk_1",
        "token": "tok_1",
        "refundable": True,
        "expected_price": 100.0
    }
    
    # Expect failure due to missing details
    result_fail = await tool_coro(
        room=room_data,
        payment_type="sms",
        runtime=mock_runtime_empty,
        session_id=None,
        price_confirmation_token=None
    )
    
    response_fail = json.loads(result_fail)
    assert response_fail["status"] == "error"
    assert "Missing verified customer details" in response_fail["error"]["message"]
    print("  [PASS] Correctly failed when details missing.")
    
    # Mock runtime WITH state
    mock_runtime_full = MagicMock()
    mock_runtime_full.tool_call_id = "call_success"
    mock_runtime_full.context = None # Ensure we rely on state
    mock_runtime_full.state = {
        "customer_details": {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com"
        },
        "user_phone": "+15551234567"
    }
    
    # Mock HTTP client AND Redis
    with patch("httpx.AsyncClient") as MockClient, \
         patch("ava_v1.tools.book.book_room.redis_get_json", return_value=None), \
         patch("ava_v1.tools.book.book_room.redis_set_json"):
        
        # Setup mock instance
        mock_instance = MockClient.return_value
        # Setup __aenter__ to return self
        mock_instance.__aenter__.return_value = mock_instance
        
        # Setup response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "key": "s3_key_123", 
            "hash": "booking_hash_abc",
            "amount": 100.0
        }
        
        # Make post async
        mock_instance.post = AsyncMock(return_value=mock_response)
        
        # Expect success
        result_success = await tool_coro(
            room=room_data,
            payment_type="sms",
            runtime=mock_runtime_full,
            session_id=None,
            price_confirmation_token=None
        )
        
        # DEBUG: Print type if assertion fails
        if not isinstance(result_success, Command):
            print(f"DEBUG: Result is {type(result_success)}: {result_success}")

        # Verify Command returned (success path returns Command)
        assert isinstance(result_success, Command)
        
        # Verify what was sent to API (via mock)
        call_args = mock_instance.post.call_args
        request_json = call_args.kwargs['json']
        
        # Crucial check: Did it use state values?
        assert request_json["customer_info"]["firstName"] == "Jane"
        assert request_json["customer_info"]["lastName"] == "Doe"
        assert request_json["customer_info"]["email"] == "jane@example.com"
        print("  [PASS] Correctly used state values for booking.")


# 4. Email Validation Integration Tests
async def test_update_customer_email_validation_gmail():
    """Test that Gmail emails pass validation (trusted provider)."""
    print("Testing Gmail email validation...")

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call_gmail"

    tool_coro = update_customer_details.coroutine

    result = await tool_coro(
        field="email",
        value="user@gmail.com",
        runtime=mock_runtime
    )

    assert isinstance(result, Command)
    assert result.update["customer_details"]["email"] == "user@gmail.com"
    print("  [PASS] Gmail email accepted")


async def test_update_customer_email_validation_disposable():
    """Test that disposable emails are rejected."""
    print("Testing disposable email rejection...")

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call_disposable"

    tool_coro = update_customer_details.coroutine

    result = await tool_coro(
        field="email",
        value="test@guerrillamail.com",
        runtime=mock_runtime
    )

    assert isinstance(result, str)
    response = json.loads(result)
    assert response["status"] == "error"
    assert "disposable" in response["message"].lower()
    print("  [PASS] Disposable email rejected")


async def test_update_customer_email_validation_no_mx():
    """Test that emails with no MX records are rejected."""
    print("Testing no MX records rejection...")

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call_no_mx"

    tool_coro = update_customer_details.coroutine

    result = await tool_coro(
        field="email",
        value="test@fakefakefake12345.com",
        runtime=mock_runtime
    )

    assert isinstance(result, str)
    response = json.loads(result)
    assert response["status"] == "error"
    assert "mail servers" in response["message"].lower()
    print("  [PASS] No MX records rejected")


async def test_update_customer_email_validation_legitimate_unknown():
    """Test that legitimate unknown domains pass after MX check."""
    print("Testing legitimate unknown domain...")

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call_legit"

    tool_coro = update_customer_details.coroutine

    result = await tool_coro(
        field="email",
        value="contact@anthropic.com",
        runtime=mock_runtime
    )

    assert isinstance(result, Command)
    assert result.update["customer_details"]["email"] == "contact@anthropic.com"
    print("  [PASS] Legitimate unknown domain accepted")


if __name__ == "__main__":
    # Allow running directly
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    test_merge_dicts_reducer()
    loop.run_until_complete(test_update_customer_details())
    loop.run_until_complete(test_book_room_state_dependency())
    loop.run_until_complete(test_update_customer_email_validation_gmail())
    loop.run_until_complete(test_update_customer_email_validation_disposable())
    loop.run_until_complete(test_update_customer_email_validation_no_mx())
    loop.run_until_complete(test_update_customer_email_validation_legitimate_unknown())
    print("\nAll tests passed successfully!")