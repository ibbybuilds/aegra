"""Unit tests for wait_for_run endpoint exception paths and edge cases."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aegra_api.api.runs import wait_for_run
from aegra_api.core.orm import Assistant as AssistantORM
from aegra_api.core.orm import Run as RunORM
from aegra_api.models import User


def _make_session_maker(session: AsyncMock) -> MagicMock:
    """Build a mock async_sessionmaker that always yields the given session."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def _make_multi_session_maker(*sessions: AsyncMock) -> MagicMock:
    """Build a mock async_sessionmaker that yields a different session each call."""
    sessions_iter = iter(sessions)

    def _factory() -> MagicMock:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=lambda: next(sessions_iter))
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    return MagicMock(side_effect=_factory)


class TestWaitForRunExceptionPaths:
    """Test exception handling and edge cases in wait_for_run endpoint."""

    @pytest.mark.asyncio
    async def test_wait_for_run_timeout(self) -> None:
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

        # Mock session for pre-wait block
        session_1 = AsyncMock()
        session_1.add = MagicMock()

        # Mock session for post-wait block
        session_2 = AsyncMock()

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

        # Pre-wait session returns assistant
        session_1.scalar.return_value = assistant
        # Post-wait session returns run
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        # Mock dependencies
        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]

            # Make wait_for raise TimeoutError
            mock_wait_for.side_effect = TimeoutError()

            # Mock the task
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            # Call the endpoint
            result = await wait_for_run(thread_id, request, user)

            # Verify timeout was handled and partial output returned
            assert result == {"partial": "output"}
            assert mock_wait_for.called

    @pytest.mark.asyncio
    async def test_wait_for_run_cancelled(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.side_effect = asyncio.CancelledError()
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            assert result == {}
            assert mock_wait_for.called

    @pytest.mark.asyncio
    async def test_wait_for_run_generic_exception_propagates(self) -> None:
        """Test that unexpected exceptions from wait_for_completion propagate as errors."""
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session_1.scalar.return_value = assistant

        mock_maker = _make_multi_session_maker(session_1)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.executor") as mock_executor,
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_executor.submit = AsyncMock()
            mock_executor.wait_for_completion = AsyncMock(side_effect=RuntimeError("Redis connection lost"))

            with pytest.raises(RuntimeError, match="Redis connection lost"):
                await wait_for_run(thread_id, request, user)

    @pytest.mark.asyncio
    async def test_wait_for_run_disappeared(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Pre-wait session returns assistant
        session_1.scalar.return_value = assistant
        # Post-wait session returns None (run disappeared)
        session_2.scalar.return_value = None

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None  # Task completes normally
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            with pytest.raises(HTTPException) as exc_info:
                await wait_for_run(thread_id, request, user)

            assert exc_info.value.status_code == 500
            assert "disappeared during execution" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wait_for_run_failed_status(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
            patch("aegra_api.api.runs.logger") as mock_logger,
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            # Verify output returned and error logged
            assert result == {"error": "execution failed"}
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_wait_for_run_interrupted_status(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            assert result == {"partial": "result", "__interrupt__": [{"value": "test"}]}

    @pytest.mark.asyncio
    async def test_wait_for_run_cancelled_status(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            assert result == {}

    @pytest.mark.asyncio
    async def test_wait_for_run_graph_not_found(self) -> None:
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
        session.add = MagicMock()

        assistant = AssistantORM(
            assistant_id="test-assistant",
            graph_id="nonexistent-graph",  # Graph doesn't exist
            config={},
            context={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.scalar.return_value = assistant

        mock_maker = _make_session_maker(session)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
        ):
            # Graph list doesn't include assistant's graph
            mock_lg_service.return_value.list_graphs.return_value = ["other-graph"]

            with pytest.raises(HTTPException) as exc_info:
                await wait_for_run(thread_id, request, user)

            assert exc_info.value.status_code == 404
            assert "Graph" in exc_info.value.detail
            assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wait_for_run_with_context_branch(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_wait_for_run_without_context_branch(self) -> None:
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

        session_1 = AsyncMock()
        session_1.add = MagicMock()
        session_2 = AsyncMock()

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

        session_1.scalar.return_value = assistant
        session_2.scalar.return_value = run_orm

        mock_maker = _make_multi_session_maker(session_1, session_2)

        with (
            patch("aegra_api.api.runs._get_session_maker", return_value=mock_maker),
            patch("aegra_api.services.run_preparation._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.services.run_preparation.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.services.run_preparation.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.services.run_preparation.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.asyncio.shield", side_effect=lambda t: t),
            patch("aegra_api.api.runs.asyncio.wait_for") as mock_wait_for,
            patch("aegra_api.api.runs.active_runs", {}),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]
            mock_wait_for.return_value = None
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            result = await wait_for_run(thread_id, request, user)

            assert result == {"result": "success"}
