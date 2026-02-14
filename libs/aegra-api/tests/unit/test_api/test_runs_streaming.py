"""Unit tests for streaming run endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aegra_api.api.runs import create_and_stream_run, stream_run
from aegra_api.core.orm import Assistant as AssistantORM
from aegra_api.core.orm import Run as RunORM
from aegra_api.models import RunCreate, User


class TestRunsStreamingEndpoints:
    """Test streaming run endpoints."""

    @pytest.fixture
    def mock_user(self) -> User:
        return User(identity="test-user", scopes=[])

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.add = MagicMock()  # session.add is synchronous
        return session

    @pytest.fixture
    def sample_assistant(self) -> AssistantORM:
        return AssistantORM(
            assistant_id="test-assistant",
            graph_id="test-graph",
            config={"configurable": {"default_key": "val"}},
            context={"default_ctx": "val"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_create_and_stream_run_success(
        self,
        mock_user: User,
        mock_session: AsyncMock,
        sample_assistant: AssistantORM,
    ) -> None:
        """Test creating and streaming a run."""
        thread_id = "test-thread-123"
        run_id = str(uuid4())

        request = RunCreate(
            assistant_id="test-assistant",
            input={"message": "stream me"},
            stream_mode=["events"],
        )

        with (
            patch("aegra_api.api.runs._validate_resume_command", new_callable=AsyncMock),
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.resolve_assistant_id",
                return_value="test-assistant",
            ),
            patch("aegra_api.api.runs.update_thread_metadata", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.uuid4", return_value=run_id),
            patch("aegra_api.api.runs.asyncio.create_task") as mock_create_task,
            patch("aegra_api.api.runs.active_runs", {}),
            patch("aegra_api.api.runs.streaming_service.stream_run_execution") as mock_stream_exec,
            patch("aegra_api.api.runs.execute_run_async", new_callable=MagicMock),
        ):
            mock_lg_service.return_value.list_graphs.return_value = ["test-graph"]

            # DB setup
            mock_session.scalar.return_value = sample_assistant

            # Mock generator for streaming response
            async def mock_generator() -> AsyncGenerator:
                yield "data"

            mock_stream_exec.return_value = mock_generator()

            response = await create_and_stream_run(thread_id, request, mock_user, mock_session)

            # Verify Response
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "text/event-stream"
            assert f"/runs/{run_id}" in response.headers["Location"]

            # Verify streaming service called
            mock_stream_exec.assert_called_once()

            # Verify DB interactions
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

            # Verify background task creation
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_run_success(self, mock_user: User, mock_session: AsyncMock) -> None:
        """Test reconnecting to existing run stream."""
        thread_id = "test-thread"
        run_id = "run-123"

        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id="agent",
            user_id=mock_user.identity,
            status="running",
            input={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_session.scalar.return_value = run_orm

        with patch("aegra_api.api.runs.streaming_service.stream_run_execution") as mock_stream_exec:
            # Mock generator
            async def mock_generator() -> AsyncGenerator:
                yield "data"

            mock_stream_exec.return_value = mock_generator()

            response = await stream_run(
                thread_id,
                run_id,
                last_event_id="evt-1",
                user=mock_user,
                session=mock_session,
            )

            assert response.status_code == 200
            mock_stream_exec.assert_called_once()
            # Verify passed params
            call_args = mock_stream_exec.call_args
            # First arg is run object, second is last_event_id
            assert call_args[0][0].run_id == run_id
            assert call_args[0][1] == "evt-1"

    @pytest.mark.asyncio
    async def test_stream_run_not_found(self, mock_user: User, mock_session: AsyncMock) -> None:
        """Test streaming non-existent run."""
        mock_session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc:
            await stream_run("t", "r", user=mock_user, session=mock_session)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_run_async_error_handling(self, mock_user: User, mock_session: AsyncMock) -> None:
        """Test that errors during streaming are properly caught and sent to broker"""
        from aegra_api.api.runs import execute_run_async
        from aegra_api.services.broker import RunBroker, broker_manager

        run_id = str(uuid4())
        thread_id = str(uuid4())
        graph_id = "test-graph"

        # Create broker to capture events
        broker = RunBroker(run_id)
        broker_manager._brokers[run_id] = broker

        async def failing_stream():
            """Stream that raises error immediately"""
            yield ("values", {"test": "data"})
            raise ValueError("Test error during streaming")

        with (
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=failing_stream(),
            ),
            patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
        ):
            mock_graph = MagicMock()
            mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
            mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session_maker.return_value = lambda: mock_session

            # Error is handled internally (no re-raise from background tasks)
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
                config={},
                context={},
                stream_mode=["values"],
            )

            # Verify error event was sent to broker
            events = []
            try:
                async for event_id, raw_event in broker.aiter():
                    events.append((event_id, raw_event))
                    if len(events) >= 5:
                        break
            except Exception:
                pass

            # Should have error event
            error_events = [evt for _, evt in events if isinstance(evt, tuple) and evt[0] == "error"]
            assert len(error_events) > 0, "Error event should be sent to broker"

            error_event = error_events[0]
            assert error_event[0] == "error"
            assert error_event[1]["error"] == "ValueError"
            assert "Test error during streaming" in str(error_event[1]["message"])
