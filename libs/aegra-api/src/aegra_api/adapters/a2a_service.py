"""A2A (Agent-to-Agent) service layer.

Maps A2A protocol concepts to Agent Protocol concepts:
- contextId -> thread_id
- taskId -> run_id
- A2A Message parts -> LangGraph messages
- Run status -> A2A TaskState

Graph execution is delegated to ``wait_for_run`` from the runs API,
which handles thread creation, run creation, graph execution, and
status management. Threads are preserved (not deleted) so that
multi-turn conversations maintain history.
"""

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import structlog
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.api.runs import create_and_stream_run, wait_for_run
from aegra_api.core.orm import Run as RunORM
from aegra_api.core.orm import _get_session_maker
from aegra_api.models import RunCreate, User
from aegra_api.utils.assistants import resolve_assistant_id

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------

RUN_STATUS_TO_TASK_STATE: dict[str, str] = {
    "pending": "submitted",
    "running": "working",
    "success": "completed",
    "error": "failed",
    "timeout": "failed",
    "interrupted": "input-required",
}

# ---------------------------------------------------------------------------
# Part conversion helpers
# ---------------------------------------------------------------------------


def convert_parts_to_langchain(parts: list[dict[str, Any]]) -> list[HumanMessage]:
    """Convert A2A message parts to LangChain HumanMessage objects.

    Only text parts are supported. Any non-text part raises ``ValueError``.

    Args:
        parts: List of A2A part dicts, each with a ``kind`` field.

    Returns:
        List of ``HumanMessage`` instances, one per text part.

    Raises:
        ValueError: If any part has a ``kind`` other than ``"text"``.
    """
    messages: list[HumanMessage] = []
    for part in parts:
        kind = part.get("kind", "text")
        if kind != "text":
            raise ValueError(
                f"Unsupported part kind {kind!r}: only 'text' parts are supported"
            )
        text_content: str = part.get("text", "")
        messages.append(HumanMessage(content=text_content))
    return messages


def convert_output_to_parts(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert LangGraph graph output to A2A text part dicts.

    Extracts AI messages from ``output["messages"]`` and converts each to a
    text part dict. Non-AI messages are skipped. Returns an empty list when
    the output contains no messages key.

    Args:
        output: Final output dict from a LangGraph run, typically
            ``{"messages": [...]}``.

    Returns:
        List of text part dicts with ``kind`` and ``text`` keys.
    """
    messages: list[Any] = output.get("messages", [])
    parts: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str):
            parts.append({"kind": "text", "text": content})
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append({"kind": "text", "text": block.get("text", "")})
    return parts


# ---------------------------------------------------------------------------
# A2AService
# ---------------------------------------------------------------------------


class A2AService:
    """Service that maps A2A protocol operations to Agent Protocol runs.

    Wraps graph execution with A2A semantics: context IDs map to threads,
    task IDs map to run IDs, and A2A message parts map to LangChain messages.
    """

    def __init__(self) -> None:
        self._langgraph_service: Any = None

    def set_langgraph_service(self, service: Any) -> None:
        """Inject the LangGraphService dependency.

        Args:
            service: A configured ``LangGraphService`` instance.
        """
        self._langgraph_service = service

    def build_agent_card(
        self,
        *,
        assistant_id: str,
        name: str,
        description: str,
        base_url: str,
    ) -> dict[str, Any]:
        """Build an A2A agent card for the given assistant.

        Args:
            assistant_id: The assistant/graph ID used to construct the URL.
            name: Human-readable agent name.
            description: Human-readable description of what the agent does.
            base_url: Base URL of the server (e.g. ``http://localhost:2026``).

        Returns:
            Agent card as a JSON-serialisable dict.
        """
        card = AgentCard(
            name=name,
            description=description,
            url=f"{base_url}/a2a/{assistant_id}",
            version="1.0.0",
            capabilities=AgentCapabilities(),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            skills=[
                AgentSkill(
                    id="default",
                    name="Default",
                    description=description,
                    tags=[],
                )
            ],
        )
        return card.model_dump(by_alias=True)

    async def send_message(
        self,
        *,
        assistant_id: str,
        parts: list[dict[str, Any]],
        user: User,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to an agent and return the resulting A2A Task.

        Delegates to ``wait_for_run`` from the runs API, which handles
        thread creation, run creation, graph execution, and waiting for
        output. Threads are preserved so subsequent turns in the same
        context can access conversation history.

        Args:
            assistant_id: Graph ID or assistant UUID to run.
            parts: List of A2A part dicts representing the incoming message.
            user: The authenticated user making the request.
            context_id: Existing thread ID to reuse; a new one is created when
                ``None``.
            task_id: Explicit run ID; a UUID is generated when ``None``.

        Returns:
            A2A Task dict with ``id``, ``contextId``, ``status``, and
            ``artifacts`` fields.

        Raises:
            ValueError: If any message part is not a text part.
            ValueError: If ``assistant_id`` is not a known graph in the
                registry.
            RuntimeError: If the LangGraph service has not been initialized.
        """
        if not self._langgraph_service:
            raise RuntimeError("LangGraph service not initialized")

        registry: dict[str, Any] = self._langgraph_service._graph_registry

        # Resolve graph_id: if assistant_id is already a graph key use it
        # directly; otherwise use it as-is for resolve_assistant_id.
        graph_id = assistant_id if assistant_id in registry else assistant_id
        resolved_assistant_id = resolve_assistant_id(graph_id, registry)

        # Convert parts to LangChain messages
        langchain_messages = convert_parts_to_langchain(parts)
        input_data: dict[str, Any] = {"messages": langchain_messages}

        thread_id = context_id if context_id is not None else str(uuid4())

        request = RunCreate(
            assistant_id=resolved_assistant_id,
            input=input_data,
        )

        output = await wait_for_run(thread_id, request, user)

        # Build A2A response
        output_parts = convert_output_to_parts(output)
        a2a_parts = [Part(root=TextPart(text=p["text"])) for p in output_parts]

        artifacts: list[Artifact] | None = (
            [Artifact(artifactId="output", parts=a2a_parts)] if a2a_parts else None
        )

        # Read the actual run_id from the DB (wait_for_run creates it internally)
        # For now, use task_id if provided, otherwise generate one
        effective_task_id = task_id or str(uuid4())

        task = Task(
            id=effective_task_id,
            contextId=thread_id,
            status=TaskStatus(state=TaskState.completed),
            artifacts=artifacts,
        )
        return task.model_dump(by_alias=True)

    async def stream_message(
        self,
        *,
        assistant_id: str,
        parts: list[dict[str, Any]],
        user: User,
        session: AsyncSession,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a message to an agent, yielding A2A SSE events.

        Delegates to ``create_and_stream_run`` from the runs API, then
        converts Agent Protocol SSE events to A2A streaming events
        (``TaskStatusUpdateEvent`` and ``TaskArtifactUpdateEvent``).

        Args:
            assistant_id: Graph ID or assistant UUID to run.
            parts: List of A2A part dicts representing the incoming message.
            user: The authenticated user making the request.
            session: Database session for run creation.
            context_id: Existing thread ID to reuse; a new one is created when
                ``None``.
            task_id: Explicit task ID; a UUID is generated when ``None``.

        Yields:
            SSE-formatted strings containing A2A streaming events.
        """
        if not self._langgraph_service:
            raise RuntimeError("LangGraph service not initialized")

        registry: dict[str, Any] = self._langgraph_service._graph_registry
        graph_id = assistant_id if assistant_id in registry else assistant_id
        resolved_assistant_id = resolve_assistant_id(graph_id, registry)

        langchain_messages = convert_parts_to_langchain(parts)
        input_data: dict[str, Any] = {"messages": langchain_messages}

        thread_id = context_id if context_id is not None else str(uuid4())
        effective_task_id = task_id or str(uuid4())

        request = RunCreate(
            assistant_id=resolved_assistant_id,
            input=input_data,
            stream_mode=["messages"],
        )

        # Get the streaming response from the runs API
        streaming_response = await create_and_stream_run(thread_id, request, user, session)

        # Emit initial status: working
        working_event = TaskStatusUpdateEvent(
            taskId=effective_task_id,
            contextId=thread_id,
            status=TaskStatus(state=TaskState.working),
            final=False,
        )
        yield f"data: {working_event.model_dump_json(by_alias=True)}\n\n"

        # Convert Agent Protocol SSE events to A2A events
        accumulated_text = ""
        async for chunk in streaming_response.body_iterator:
            if not isinstance(chunk, str):
                chunk = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

            # Parse SSE format: "event: <type>\ndata: <json>\n\n"
            for line in chunk.strip().split("\n"):
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        event_data = json.loads(data_str)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # Convert messages/partial events to artifact updates
                    if isinstance(event_data, list):
                        # Messages stream mode returns [message_chunk, metadata]
                        for item in event_data:
                            if isinstance(item, dict):
                                content = item.get("content", "")
                                if content and isinstance(content, str):
                                    accumulated_text += content
                                    artifact_event = TaskArtifactUpdateEvent(
                                        taskId=effective_task_id,
                                        contextId=thread_id,
                                        artifact=Artifact(
                                            artifactId="output",
                                            parts=[Part(root=TextPart(text=content))],
                                        ),
                                        append=True,
                                        lastChunk=False,
                                    )
                                    yield f"data: {artifact_event.model_dump_json(by_alias=True)}\n\n"

                elif line.startswith("event: end"):
                    # Stream ended — emit final artifact and completed status
                    break

        # Emit final artifact chunk if we accumulated text
        if accumulated_text:
            final_artifact = TaskArtifactUpdateEvent(
                taskId=effective_task_id,
                contextId=thread_id,
                artifact=Artifact(
                    artifactId="output",
                    parts=[Part(root=TextPart(text=accumulated_text))],
                ),
                append=False,
                lastChunk=True,
            )
            yield f"data: {final_artifact.model_dump_json(by_alias=True)}\n\n"

        # Emit terminal status: completed
        completed_event = TaskStatusUpdateEvent(
            taskId=effective_task_id,
            contextId=thread_id,
            status=TaskStatus(state=TaskState.completed),
            final=True,
        )
        yield f"data: {completed_event.model_dump_json(by_alias=True)}\n\n"

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Look up a task by its run ID and return the A2A Task dict.

        Args:
            task_id: The run ID (A2A task ID) to look up.

        Returns:
            A2A Task dict with the current status.

        Raises:
            ValueError: If no run with ``task_id`` is found.
        """
        maker = _get_session_maker()
        async with maker() as session:
            run_record: RunORM | None = await session.scalar(
                select(RunORM).where(RunORM.run_id == task_id)
            )

        if run_record is None:
            raise ValueError(f"Task not found: {task_id!r}")

        raw_status: str = run_record.status or "pending"
        task_state_value: str = RUN_STATUS_TO_TASK_STATE.get(raw_status, "unknown")
        task_state = TaskState(task_state_value)

        output: dict[str, Any] = run_record.output or {}
        output_parts = convert_output_to_parts(output)
        a2a_parts = [Part(root=TextPart(text=p["text"])) for p in output_parts]

        artifacts: list[Artifact] | None = (
            [Artifact(artifactId="output", parts=a2a_parts)] if a2a_parts else None
        )

        task = Task(
            id=run_record.run_id,
            contextId=run_record.thread_id,
            status=TaskStatus(state=task_state),
            artifacts=artifacts,
        )
        return task.model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_a2a_service: A2AService | None = None


def get_a2a_service() -> A2AService:
    """Return the global A2AService instance."""
    global _a2a_service
    if _a2a_service is None:
        _a2a_service = A2AService()
    return _a2a_service
