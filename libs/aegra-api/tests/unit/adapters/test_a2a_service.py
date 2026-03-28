"""Unit tests for the A2A service layer."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from aegra_api.adapters.a2a_service import (
    RUN_STATUS_TO_TASK_STATE,
    A2AService,
    convert_output_to_parts,
    convert_parts_to_langchain,
)
from aegra_api.models.auth import User

_TEST_USER = User(identity="test-user", is_authenticated=True, permissions=[])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(registry: dict[str, Any]) -> A2AService:
    """Create an A2AService with a minimal mocked LangGraphService."""
    langgraph_service = MagicMock()
    langgraph_service._graph_registry = registry
    service = A2AService()
    service.set_langgraph_service(langgraph_service)
    return service


# ---------------------------------------------------------------------------
# convert_parts_to_langchain
# ---------------------------------------------------------------------------


def test_text_part_becomes_human_message() -> None:
    """A text part dict is converted to a single HumanMessage."""
    from langchain_core.messages import HumanMessage

    parts = [{"kind": "text", "text": "hello world"}]
    result = convert_parts_to_langchain(parts)

    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "hello world"


def test_non_text_part_raises_error() -> None:
    """A non-text part raises ValueError."""
    parts = [{"kind": "file", "data": "base64stuff"}]

    with pytest.raises(ValueError, match="Unsupported part kind"):
        convert_parts_to_langchain(parts)


def test_multiple_text_parts_become_multiple_messages() -> None:
    """Multiple text parts produce one HumanMessage each."""
    from langchain_core.messages import HumanMessage

    parts = [
        {"kind": "text", "text": "first"},
        {"kind": "text", "text": "second"},
    ]
    result = convert_parts_to_langchain(parts)

    assert len(result) == 2
    assert all(isinstance(m, HumanMessage) for m in result)
    assert result[0].content == "first"
    assert result[1].content == "second"


def test_empty_parts_list_returns_empty_messages() -> None:
    """An empty parts list produces an empty message list."""
    result = convert_parts_to_langchain([])
    assert result == []


# ---------------------------------------------------------------------------
# convert_output_to_parts
# ---------------------------------------------------------------------------


def test_string_content_becomes_text_part() -> None:
    """An AIMessage with string content becomes a single text part."""
    output: dict[str, Any] = {"messages": [AIMessage(content="Response text")]}
    result = convert_output_to_parts(output)

    assert len(result) == 1
    assert result[0]["kind"] == "text"
    assert result[0]["text"] == "Response text"


def test_empty_output_returns_empty_parts() -> None:
    """An empty output dict produces an empty parts list."""
    result = convert_output_to_parts({})
    assert result == []


def test_output_without_messages_key_returns_empty_parts() -> None:
    """Output without a 'messages' key produces an empty parts list."""
    result = convert_output_to_parts({"state": "done"})
    assert result == []


def test_non_ai_messages_are_skipped() -> None:
    """HumanMessage and other non-AI messages are filtered out."""
    from langchain_core.messages import HumanMessage

    output: dict[str, Any] = {
        "messages": [
            HumanMessage(content="user input"),
            AIMessage(content="ai response"),
        ]
    }
    result = convert_output_to_parts(output)

    assert len(result) == 1
    assert result[0]["text"] == "ai response"


def test_list_content_with_text_blocks_extracted() -> None:
    """AIMessage with list content containing text blocks is converted correctly."""
    output: dict[str, Any] = {
        "messages": [
            AIMessage(content=[{"type": "text", "text": "block text"}])
        ]
    }
    result = convert_output_to_parts(output)

    assert len(result) == 1
    assert result[0]["text"] == "block text"


def test_list_content_non_text_blocks_skipped() -> None:
    """Non-text blocks in list content are silently skipped."""
    output: dict[str, Any] = {
        "messages": [
            AIMessage(content=[{"type": "tool_use", "id": "123", "name": "foo"}])
        ]
    }
    result = convert_output_to_parts(output)
    assert result == []


# ---------------------------------------------------------------------------
# RUN_STATUS_TO_TASK_STATE
# ---------------------------------------------------------------------------


def test_all_statuses_mapped() -> None:
    """Every run status in RUN_STATUS_TO_TASK_STATE maps to a valid TaskState value."""
    from a2a.types import TaskState

    valid_states = {s.value for s in TaskState}

    for run_status, task_state_value in RUN_STATUS_TO_TASK_STATE.items():
        assert task_state_value in valid_states, (
            f"Run status {run_status!r} maps to {task_state_value!r} "
            f"which is not a valid TaskState"
        )


def test_status_mapping_covers_known_run_statuses() -> None:
    """The expected run statuses are present in the mapping."""
    expected = {"pending", "running", "success", "error", "timeout", "interrupted"}
    assert expected.issubset(set(RUN_STATUS_TO_TASK_STATE.keys()))


# ---------------------------------------------------------------------------
# A2AService.build_agent_card
# ---------------------------------------------------------------------------


def test_generates_card_with_correct_fields() -> None:
    """build_agent_card returns an agent card with the expected structure."""
    service = _make_service({})

    card = service.build_agent_card(
        assistant_id="my-agent",
        name="My Agent",
        description="Does stuff",
        base_url="http://localhost:2026",
    )

    assert card["name"] == "My Agent"
    assert card["description"] == "Does stuff"
    assert card["url"] == "http://localhost:2026/a2a/my-agent"
    assert "capabilities" in card
    assert isinstance(card["skills"], list)
    assert len(card["skills"]) >= 1


def test_card_url_uses_assistant_id() -> None:
    """build_agent_card embeds the assistant_id in the URL path."""
    service = _make_service({})

    card = service.build_agent_card(
        assistant_id="special-graph",
        name="Special",
        description="Special graph",
        base_url="https://example.com",
    )

    assert card["url"] == "https://example.com/a2a/special-graph"


# ---------------------------------------------------------------------------
# A2AService.send_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_delegates_to_wait_for_run() -> None:
    """send_message invokes wait_for_run and returns a Task dict."""
    registry: dict[str, Any] = {"my_graph": {"file_path": "g.py", "export_name": "graph"}}
    service = _make_service(registry)

    fake_output: dict[str, Any] = {
        "messages": [AIMessage(content="Graph output")]
    }

    with patch(
        "aegra_api.adapters.a2a_service.wait_for_run",
        new=AsyncMock(return_value=fake_output),
    ):
        result = await service.send_message(
            assistant_id="my_graph",
            parts=[{"kind": "text", "text": "Hello"}],
            user=_TEST_USER,
            context_id="ctx-thread",
        )

    assert result["contextId"] == "ctx-thread"
    assert result["status"]["state"].value == "completed"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["parts"][0]["text"] == "Graph output"


@pytest.mark.asyncio
async def test_send_message_generates_thread_id_when_none() -> None:
    """send_message generates a thread_id when context_id is not supplied."""
    registry: dict[str, Any] = {"agent": {"file_path": "a.py", "export_name": "graph"}}
    service = _make_service(registry)

    captured_thread_ids: list[str] = []

    async def _capture_wait(thread_id: str, request: Any, user: Any) -> dict[str, Any]:
        captured_thread_ids.append(thread_id)
        return {}

    with patch(
        "aegra_api.adapters.a2a_service.wait_for_run",
        side_effect=_capture_wait,
    ):
        result = await service.send_message(
            assistant_id="agent",
            parts=[{"kind": "text", "text": "hi"}],
            user=_TEST_USER,
        )

    assert len(captured_thread_ids) == 1
    assert isinstance(captured_thread_ids[0], str)
    assert len(captured_thread_ids[0]) > 0
    assert result["contextId"] is not None


@pytest.mark.asyncio
async def test_send_message_raises_on_non_text_parts() -> None:
    """send_message propagates ValueError from convert_parts_to_langchain."""
    registry: dict[str, Any] = {"graph": {}}
    service = _make_service(registry)

    with pytest.raises(ValueError, match="Unsupported part kind"):
        await service.send_message(
            assistant_id="graph",
            parts=[{"kind": "image", "url": "http://example.com/img.png"}],
            user=_TEST_USER,
        )


@pytest.mark.asyncio
async def test_send_message_returns_no_artifacts_when_empty_output() -> None:
    """send_message returns None artifacts when the graph emits no AI messages."""
    registry: dict[str, Any] = {"graph": {}}
    service = _make_service(registry)

    with patch(
        "aegra_api.adapters.a2a_service.wait_for_run",
        new=AsyncMock(return_value={}),
    ):
        result = await service.send_message(
            assistant_id="graph",
            parts=[{"kind": "text", "text": "hello"}],
            user=_TEST_USER,
        )

    assert result["artifacts"] is None
