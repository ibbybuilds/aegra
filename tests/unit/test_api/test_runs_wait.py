"""Unit tests for wait_for_run endpoint exception paths and edge cases."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from agent_server.api.runs import wait_for_run
from agent_server.core.orm import Assistant as AssistantORM
from agent_server.core.orm import Run as RunORM
from agent_server.models import User


class TestWaitForRunExceptionPaths:
    """Test exception handling and edge cases in wait_for_run endpoint."""

    @pytest.mark.asyncio
    async def test_wait_for_run_timeout(self):
        """Test that TimeoutError is handled gracefully and returns current state."""
        # Setup mocks
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        # Mock request
        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        # Mock session
        session = AsyncMock()

        # Mock assistant
        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock run that will be returned after timeout
        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="running",  # Still running after timeout
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={"partial": "output"},
            error_message=None,
        )

        # Configure session.scalar to return assistant then run
        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        # Mock dependencies
        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]

            # Make wait_for raise TimeoutError
            mock_wait_for.side_effect = TimeoutError()

            # Mock the task
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            # Call the endpoint
            result = await wait_for_run(thread_id, request, user, session)

            # Verify timeout was handled and partial output returned
            assert result == {"partial": "output"}
            assert mock_wait_for.called

    @pytest.mark.asyncio
    async def test_wait_for_run_cancelled(self):
        """Test that CancelledError is handled gracefully."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="interrupted",
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={},
            error_message=None,
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.side_effect = asyncio.CancelledError()
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {}
            assert mock_wait_for.called

    @pytest.mark.asyncio
    async def test_wait_for_run_generic_exception(self):
        """Test that generic Exception is handled gracefully."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="error",
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={},
            error_message="Something went wrong",
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.side_effect = Exception("Test exception")
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {}
            assert mock_wait_for.called

    @pytest.mark.asyncio
    async def test_wait_for_run_disappeared(self):
        """Test that HTTPException 500 is raised if run disappears during execution."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # First call returns assistant, second call returns None (run disappeared)
        session.scalar.side_effect = [assistant, None]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None  # Task completes normally
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            with pytest.raises(HTTPException) as exc_info:
                await wait_for_run(thread_id, request, user, session)

            assert exc_info.value.status_code == 500
            assert "disappeared during execution" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wait_for_run_failed_status(self):
        """Test that failed runs return output and log error."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="error",
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={"error": "execution failed"},
            error_message="Graph execution error",
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
            patch("agent_server.api.runs.logger") as mock_logger,
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            # Verify output returned and error logged
            assert result == {"error": "execution failed"}
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_wait_for_run_interrupted_status(self):
        """Test that interrupted runs return partial output."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = ["agent"]
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="interrupted",
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={"partial": "result", "__interrupt__": [{"value": "test"}]},
            error_message=None,
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {"partial": "result", "__interrupt__": [{"value": "test"}]}

    @pytest.mark.asyncio
    async def test_wait_for_run_cancelled_status(self):
        """Test that cancelled runs return empty output."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="interrupted",
            input={"message": "test"},
            config={},
            context={},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={},
            error_message=None,
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {}

    @pytest.mark.asyncio
    async def test_wait_for_run_graph_not_found(self):
        """Test that HTTPException 404 is raised if assistant's graph doesn't exist."""
        thread_id = "test-thread-123"
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = None
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="nonexistent-graph",  # Graph doesn't exist
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.scalar.return_value = assistant

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
        ):
            # Graph list doesn't include assistant's graph
            mock_lg_service.return_value.list_graphs.return_value = ["other-graph"]

            with pytest.raises(HTTPException) as exc_info:
                await wait_for_run(thread_id, request, user, session)

            assert exc_info.value.status_code == 404
            assert "Graph" in exc_info.value.detail
            assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wait_for_run_with_context_branch(self):
        """Test the context branch where context is provided."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {}
        request.context = {"user_id": "123", "session": "abc"}  # Context provided
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="success",
            input={"message": "test"},
            config={"configurable": {"user_id": "123", "session": "abc"}},
            context={"user_id": "123", "session": "abc"},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={"result": "success"},
            error_message=None,
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_wait_for_run_without_context_branch(self):
        """Test the else branch where context is not provided."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())
        user = User(identity="test-user", scopes=[])

        request = MagicMock()
        request.assistant_id = "test-assistant"
        request.input = {"message": "test"}
        request.command = None
        request.config = {"configurable": {"thread_id": thread_id}}
        request.context = None  # No context provided
        request.checkpoint = None
        request.stream_mode = None
        request.interrupt_before = None
        request.interrupt_after = None
        request.multitask_strategy = None
        request.stream_subgraphs = False

        session = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="test-assistant",
            status="success",
            input={"message": "test"},
            config={"configurable": {"thread_id": thread_id}},
            context={"thread_id": thread_id},
            user_id="test-user",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            output={"result": "success"},
            error_message=None,
        )

        session.scalar.side_effect = [assistant, run_orm]
        session.refresh = AsyncMock()

        with (
            patch(
                "agent_server.api.runs._validate_resume_command", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "agent_server.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("agent_server.api.runs.set_thread_status", new_callable=AsyncMock),
            patch(
                "agent_server.api.runs.update_thread_metadata", new_callable=AsyncMock
            ),
            patch("agent_server.api.runs.uuid4", return_value=run_id),
            patch("agent_server.api.runs.asyncio.create_task") as mock_create_task,
            patch("agent_server.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("agent_server.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user, session)

            assert result == {"result": "success"}
