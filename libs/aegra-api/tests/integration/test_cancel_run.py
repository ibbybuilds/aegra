"""Integration tests for run cancellation.

Tests verify that cancelling a run properly cancels the asyncio task
and sets the run status to 'interrupted'.

Addresses GitHub Issue #132: Cancel endpoint doesn't cancel asyncio task
"""

import asyncio
import contextlib
from uuid import uuid4

import pytest

from aegra_api.api.runs import active_runs
from aegra_api.services.broker import RunBroker, broker_manager
from aegra_api.services.streaming_service import streaming_service


@pytest.mark.asyncio
class TestCancelRun:
    """Test run cancellation properly cancels asyncio tasks"""

    @pytest.fixture
    def run_id(self) -> str:
        return str(uuid4())

    async def test_cancel_already_completed_run_returns_true(self, run_id: str):
        """Test that cancelling an already completed run doesn't error"""
        # No task registered for this run_id
        result = await streaming_service.cancel_run(run_id)
        # Should return True even if no task to cancel
        assert result is True

    async def test_cancel_background_task_returns_false_for_missing_task(self, run_id: str):
        """Test that _cancel_background_task returns False when no task exists"""
        result = streaming_service._cancel_background_task(run_id)
        assert result is False

    async def test_cancel_background_task_returns_false_for_completed_task(self, run_id: str):
        """Test that _cancel_background_task returns False for completed task"""

        # Create a completed task
        async def quick_task():
            return "done"

        task = asyncio.create_task(quick_task())
        await task  # Wait for completion

        active_runs[run_id] = task

        result = streaming_service._cancel_background_task(run_id)
        assert result is False

        active_runs.pop(run_id, None)

    async def test_cancel_background_task_returns_true_for_running_task(self, run_id: str):
        """Test that _cancel_background_task returns True for running task"""

        # Create a long-running task
        async def slow_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(slow_task())
        active_runs[run_id] = task

        result = streaming_service._cancel_background_task(run_id)
        assert result is True
        assert task.cancelled() or task.cancelling()

        # Cleanup
        with contextlib.suppress(asyncio.CancelledError):
            await task
        active_runs.pop(run_id, None)

    async def test_cancel_run_calls_cancel_background_task(self, run_id: str):
        """Test that cancel_run actually tries to cancel the asyncio task"""
        # Track if cancel was called
        task_was_cancelled = False

        async def cancellable_task():
            nonlocal task_was_cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                task_was_cancelled = True
                raise

        task = asyncio.create_task(cancellable_task())
        active_runs[run_id] = task

        # Create a broker for the run
        broker = RunBroker(run_id)
        if not hasattr(broker_manager, "_brokers"):
            broker_manager._brokers = {}
        broker_manager._brokers[run_id] = broker

        # Cancel the run
        result = await streaming_service.cancel_run(run_id)
        assert result is True

        # Wait for task to be cancelled
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)

        assert task_was_cancelled or task.cancelled(), "Task should have been cancelled"

        # Cleanup
        active_runs.pop(run_id, None)
        broker_manager._brokers.pop(run_id, None)

    async def test_interrupt_run_calls_cancel_background_task(self, run_id: str):
        """Test that interrupt_run actually tries to cancel the asyncio task"""
        task_was_cancelled = False

        async def cancellable_task():
            nonlocal task_was_cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                task_was_cancelled = True
                raise

        task = asyncio.create_task(cancellable_task())
        active_runs[run_id] = task

        broker = RunBroker(run_id)
        if not hasattr(broker_manager, "_brokers"):
            broker_manager._brokers = {}
        broker_manager._brokers[run_id] = broker

        # Interrupt the run
        result = await streaming_service.interrupt_run(run_id)
        assert result is True

        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)

        assert task_was_cancelled or task.cancelled(), "Task should have been cancelled"

        active_runs.pop(run_id, None)
        broker_manager._brokers.pop(run_id, None)


@pytest.mark.asyncio
class TestCancelRunStatusNotOverwritten:
    """Test that cancelled run status is not overwritten to 'success'

    When a task is cancelled via asyncio.Task.cancel(), it will raise
    CancelledError which is caught by execute_run_async and the status
    is set to 'interrupted'. The normal completion path (which would
    set status to 'success') is never reached.
    """

    @pytest.fixture
    def run_id(self) -> str:
        return str(uuid4())

    async def test_cancelled_task_raises_cancelled_error(self, run_id: str):
        """Verify that cancelled task properly raises CancelledError"""
        completed_normally = False
        was_cancelled = False

        async def task_with_completion_check():
            nonlocal completed_normally, was_cancelled
            try:
                await asyncio.sleep(10)
                completed_normally = True
            except asyncio.CancelledError:
                was_cancelled = True
                raise

        task = asyncio.create_task(task_with_completion_check())
        active_runs[run_id] = task

        # Let it start
        await asyncio.sleep(0.1)

        # Cancel using our method
        streaming_service._cancel_background_task(run_id)

        # Wait for cancellation to propagate
        with pytest.raises(asyncio.CancelledError):
            await task

        assert was_cancelled, "Task should have received CancelledError"
        assert not completed_normally, "Task should NOT have completed normally"

        active_runs.pop(run_id, None)
