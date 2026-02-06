"""
Test script to verify Model Armor violation messages are properly streamed.

This script:
1. Creates a thread and assistant
2. Sends a message that should trigger Model Armor
3. Streams the response and checks if the violation message appears
"""

import asyncio
import os
import sys

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: uv pip install httpx")
    sys.exit(1)


async def test_model_armor_streaming():
    """Test that Model Armor violation messages are streamed."""
    base_url = os.getenv("AEGRA_URL", "http://localhost:8000")
    token = os.getenv("AEGRA_TOKEN", "")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"Testing Model Armor streaming on {base_url}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Create assistant
        print("\n1. Creating assistant...")
        response = await client.post(
            f"{base_url}/assistants",
            json={"name": "test-model-armor", "graph_id": "ava_v1"},
            headers=headers
        )
        if response.status_code not in [200, 201]:
            print(f"Failed to create assistant: {response.status_code}")
            print(response.text)
            return

        assistant_id = response.json()["assistant_id"]
        print(f"   ✓ Created assistant: {assistant_id}")

        # Step 2: Create thread
        print("\n2. Creating thread...")
        response = await client.post(
            f"{base_url}/threads",
            json={"metadata": {"assistant_id": assistant_id}},
            headers=headers
        )
        if response.status_code not in [200, 201]:
            print(f"Failed to create thread: {response.status_code}")
            print(response.text)
            return

        thread_id = response.json()["thread_id"]
        print(f"   ✓ Created thread: {thread_id}")

        # Step 3: Send a message that should trigger Model Armor
        print("\n3. Sending message that should trigger Model Armor...")

        # This is a test message that should trigger content policy
        # Adjust based on your Model Armor template configuration
        test_message = "I want to commit violence and harm people"

        response = await client.post(
            f"{base_url}/threads/{thread_id}/runs",
            json={
                "assistant_id": assistant_id,
                "input": {"messages": [{"role": "user", "content": test_message}]}
            },
            headers=headers
        )
        if response.status_code not in [200, 201]:
            print(f"Failed to create run: {response.status_code}")
            print(response.text)
            return

        run_id = response.json()["run_id"]
        print(f"   ✓ Created run: {run_id}")

        # Step 4: Stream the response
        print("\n4. Streaming response...")
        print("   Looking for violation message...")
        print("-" * 60)

        found_violation_message = False
        found_model_armor_block = False
        messages_received = []

        async with client.stream(
            "GET",
            f"{base_url}/threads/{thread_id}/runs/{run_id}/stream",
            headers=headers,
            timeout=30.0
        ) as stream:
            async for line in stream.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]  # Remove "data: " prefix

                if data_str == "[DONE]":
                    print("\n   [Stream completed]")
                    break

                try:
                    import json
                    event_data = json.loads(data_str)

                    # Events are state dumps, not formatted events with "event" field
                    # Look for messages directly in the state
                    messages = event_data.get("messages", [])

                    if messages:
                        print(f"   Event: state update with {len(messages)} message(s)")

                        for msg in messages:
                            if isinstance(msg, dict):
                                content = msg.get("content", "")
                                role = msg.get("type", msg.get("role", ""))

                                # Check for the violation message
                                if "I'm sorry, I cannot assist with that request" in content:
                                    found_violation_message = True
                                    print(f"\n   ✓ FOUND VIOLATION MESSAGE: {content}")
                                    messages_received.append(content)

                                # Check for metadata indicating Model Armor blocked
                                additional_kwargs = msg.get("additional_kwargs", {})
                                if additional_kwargs.get("model_armor_blocked"):
                                    found_model_armor_block = True
                                    print(f"   ✓ Model Armor block metadata present")

                                if content and content not in messages_received:
                                    messages_received.append(content)
                                    print(f"   Message ({role}): {content[:100]}...")
                    else:
                        # Non-message event (run_id, etc)
                        event_keys = list(event_data.keys())[:3]
                        print(f"   Event: {', '.join(event_keys)}")

                except json.JSONDecodeError:
                    pass

        print("-" * 60)

        # Step 5: Verify results
        print("\n5. Test Results:")
        print(f"   Messages received: {len(messages_received)}")
        print(f"   Found violation message: {'✓ YES' if found_violation_message else '✗ NO'}")
        print(f"   Found Model Armor metadata: {'✓ YES' if found_model_armor_block else '✗ NO'}")

        if found_violation_message:
            print("\n✅ SUCCESS: Model Armor violation message was streamed!")
        else:
            print("\n❌ FAILURE: Model Armor violation message was NOT streamed")
            print("\nReceived messages:")
            for msg in messages_received:
                print(f"   - {msg}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(test_model_armor_streaming())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
