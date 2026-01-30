"""
Debug test to understand checkpoint loading behavior
"""

import pytest

from tests.e2e._utils import elog, get_e2e_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_run_without_input_sees_injected():
    """
    Test creating a run WITHOUT any input messages.
    If the graph properly loads the checkpoint, it should see the injected messages
    and process them.
    """
    client = get_e2e_client()

    # 1. Create assistant
    assistant = await client.assistants.create(
        graph_id="ava_v1",
        config={"tags": ["debug-checkpoint-test"]},
        if_exists="do_nothing",
    )
    elog("Assistant created", assistant)

    # 2. Create thread
    thread = await client.threads.create(metadata={"graph_id": "ava"})
    thread_id = thread["thread_id"]
    elog("Thread created", thread)

    # 3. Inject a human message asking a question
    human_message = {
        "type": "human",
        "content": "What's the weather in San Francisco?",
        "id": "injected_human_001",
    }

    elog("Injecting human message", human_message)
    await client.threads.update_state(
        thread_id=thread_id,
        values={
            "messages": [human_message],
            # VFS state fields (multi-value for parallel tool call support)
            # Hotel search state
            "hotelSearchKeys": [],
            "hotelMeta": {},
            "hotelCursors": {},
            "hotelParams": {},
            # Room search state
            "roomSearchKeys": [],
            "roomMeta": {},
            "roomCursors": {},
            "roomParams": {},
            # Token management (auto-populated by tools, initialize as empty)
            "searchKeyToToken": {},
            "hotelIdToSearchKey": {},
            "rateKeyToToken": {},
            # Other state fields
            "rateKeyToHotelId": {},
            "priceCheckResults": {},
            "location": None,
            "structured_response": None,
        },
    )

    # 4. Verify message is in state
    state = await client.threads.get_state(thread_id=thread_id)
    elog("State after injection", state)
    messages = state.get("values", {}).get("messages", [])
    assert len(messages) == 1, "Should have 1 injected message"

    # 5. Create run WITHOUT any input (empty input)
    # The graph should process the injected message from the checkpoint
    elog("Creating run with NO input (should process injected message)", None)
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={},  # ← Empty input! Should use checkpoint state
    )
    elog("Run created", run)

    # 6. Wait for completion
    elog("Waiting for run...", None)
    final_state = await client.runs.join(thread_id, run["run_id"])
    elog("Run completed", final_state)

    # 7. Check if agent responded to the injected message
    if "messages" in final_state:
        final_messages = final_state["messages"]
    else:
        final_messages = final_state.get("values", {}).get("messages", [])

    elog(f"Final message count: {len(final_messages)}", None)
    elog("All messages", final_messages)

    # Should have: injected_human + ai_response (at least 2)
    assert len(final_messages) >= 2, (
        f"Expected at least 2 messages, got {len(final_messages)}"
    )

    # Check if AI responded
    ai_messages = [m for m in final_messages if m.get("type") == "ai"]
    assert len(ai_messages) > 0, "Should have at least one AI response"

    elog("✅ Agent processed the injected message!", None)
