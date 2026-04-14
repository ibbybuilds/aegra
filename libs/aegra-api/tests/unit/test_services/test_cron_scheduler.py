"""Unit tests for CronScheduler background task.

All external dependencies (database, run preparation) are mocked.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from aegra_api.services.cron_scheduler import CronScheduler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cron_orm(
    *,
    cron_id: str = "cron-001",
    assistant_id: str = "asst-001",
    thread_id: str | None = None,
    user_id: str = "test-user",
    schedule: str = "*/5 * * * *",
    payload: dict[str, Any] | None = None,
    enabled: bool = True,
    end_time: datetime | None = None,
    next_run_date: datetime | None = None,
) -> Mock:
    """Build a mock CronORM row for scheduler tests."""
    now = datetime.now(UTC)
    cron = Mock()
    cron.cron_id = cron_id
    cron.assistant_id = assistant_id
    cron.thread_id = thread_id
    cron.user_id = user_id
    cron.schedule = schedule
    cron.payload = payload if payload is not None else {"input": {"msg": "tick"}}
    cron.enabled = enabled
    cron.end_time = end_time
    cron.next_run_date = next_run_date or now
    return cron


# ---------------------------------------------------------------------------
# Lifecycle: start / stop
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    """Test CronScheduler.start() and stop()."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        scheduler = CronScheduler()
        with patch.object(scheduler, "_loop", new_callable=AsyncMock):
            await scheduler.start()
            assert scheduler._task is not None
            assert scheduler._running is True
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        scheduler = CronScheduler()
        with patch.object(scheduler, "_loop", new_callable=AsyncMock):
            await scheduler.start()
            await scheduler.stop()
            assert scheduler._running is False
            assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        scheduler = CronScheduler()
        await scheduler.stop()  # should not raise
        assert scheduler._running is False
        assert scheduler._task is None


# ---------------------------------------------------------------------------
# _tick
# ---------------------------------------------------------------------------


class TestSchedulerTick:
    """Test CronScheduler._tick()."""

    @pytest.mark.asyncio
    async def test_tick_no_due_crons(self) -> None:
        scheduler = CronScheduler()

        mock_session = AsyncMock()
        scalars = Mock()
        scalars.all.return_value = []
        mock_session.scalars.return_value = scalars

        mock_maker = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "aegra_api.services.cron_scheduler._get_session_maker",
            return_value=mock_maker,
        ):
            await scheduler._tick()

    @pytest.mark.asyncio
    async def test_tick_fires_due_crons(self) -> None:
        scheduler = CronScheduler()

        cron = _make_cron_orm()
        mock_session = AsyncMock()
        scalars = Mock()
        scalars.all.return_value = [cron]
        mock_session.scalars.return_value = scalars
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_maker = Mock(return_value=mock_session)

        with (
            patch(
                "aegra_api.services.cron_scheduler._get_session_maker",
                return_value=mock_maker,
            ),
            patch.object(scheduler, "_fire_cron", new_callable=AsyncMock) as mock_fire,
        ):
            await scheduler._tick()
            mock_fire.assert_awaited_once_with(mock_session, cron)

    @pytest.mark.asyncio
    async def test_tick_continues_on_fire_error(self) -> None:
        """A failing cron should not prevent other crons from firing."""
        scheduler = CronScheduler()

        cron_ok = _make_cron_orm(cron_id="ok")
        cron_fail = _make_cron_orm(cron_id="fail")
        mock_session = AsyncMock()
        scalars = Mock()
        scalars.all.return_value = [cron_fail, cron_ok]
        mock_session.scalars.return_value = scalars
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_maker = Mock(return_value=mock_session)

        call_count = 0

        async def _side_effect(_session: Any, cron: Any) -> None:
            nonlocal call_count
            call_count += 1
            if cron.cron_id == "fail":
                raise RuntimeError("boom")

        with (
            patch(
                "aegra_api.services.cron_scheduler._get_session_maker",
                return_value=mock_maker,
            ),
            patch.object(scheduler, "_fire_cron", side_effect=_side_effect),
        ):
            await scheduler._tick()
            assert call_count == 2


# ---------------------------------------------------------------------------
# _fire_cron
# ---------------------------------------------------------------------------


class TestFireCron:
    """Test CronScheduler._fire_cron()."""

    @pytest.mark.asyncio
    async def test_creates_run_and_advances(self) -> None:
        scheduler = CronScheduler()
        cron = _make_cron_orm(
            payload={"input": {"msg": "hi"}},
            end_time=None,
        )
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.return_value = ("run-1", Mock(), None)
            await scheduler._fire_cron(mock_session, cron)

            mock_prepare.assert_awaited_once()
            # Should advance next_run_date
            mock_session.execute.assert_awaited_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_cron_thread_id_when_set(self) -> None:
        scheduler = CronScheduler()
        cron = _make_cron_orm(thread_id="t-bound", end_time=None)
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.return_value = ("run-1", Mock(), None)
            await scheduler._fire_cron(mock_session, cron)

            call_args = mock_prepare.call_args
            assert call_args[0][1] == "t-bound"

    @pytest.mark.asyncio
    async def test_generates_uuid_thread_when_no_thread_id(self) -> None:
        scheduler = CronScheduler()
        cron = _make_cron_orm(thread_id=None, end_time=None)
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.return_value = ("run-1", Mock(), None)
            await scheduler._fire_cron(mock_session, cron)

            call_args = mock_prepare.call_args
            thread_id = call_args[0][1]
            assert thread_id is not None
            assert thread_id != ""
            assert len(thread_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_disables_cron_when_past_end_time(self) -> None:
        scheduler = CronScheduler()
        past = datetime.now(UTC) - timedelta(hours=1)
        cron = _make_cron_orm(end_time=past)
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.return_value = ("run-1", Mock(), None)
            await scheduler._fire_cron(mock_session, cron)

            # Should set enabled=False via execute
            mock_session.execute.assert_awaited_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_http_exception_in_run_creation(self) -> None:
        """HTTPException from _prepare_run should be caught and logged, not raised."""
        scheduler = CronScheduler()
        cron = _make_cron_orm(end_time=None)
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.side_effect = HTTPException(404, "assistant not found")
            # Should not raise
            await scheduler._fire_cron(mock_session, cron)
            # Should still advance
            mock_session.execute.assert_awaited_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_advances_next_run_date_on_non_http_error(self) -> None:
        """Non-HTTPException from _prepare_run must not skip the schedule advance."""
        scheduler = CronScheduler()
        cron = _make_cron_orm(end_time=None)
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.side_effect = RuntimeError("database connection lost")
            # Should not raise
            await scheduler._fire_cron(mock_session, cron)
            # next_run_date must still be advanced
            mock_session.execute.assert_awaited_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_builds_run_create_from_payload(self) -> None:
        scheduler = CronScheduler()
        cron = _make_cron_orm(
            payload={
                "input": {"data": True},
                "config": {"k": "v"},
                "interrupt_before": ["step1"],
                "stream_mode": "values",
            },
            end_time=None,
        )
        cron.end_time = None
        mock_session = AsyncMock()

        with patch(
            "aegra_api.services.cron_scheduler._prepare_run",
            new_callable=AsyncMock,
        ) as mock_prepare:
            mock_prepare.return_value = ("run-1", Mock(), None)
            await scheduler._fire_cron(mock_session, cron)

            call_args = mock_prepare.call_args
            run_request = call_args[0][2]
            assert run_request.input == {"data": True}
            assert run_request.config == {"k": "v"}
            assert run_request.interrupt_before == ["step1"]
            assert run_request.stream_mode == "values"


# ---------------------------------------------------------------------------
# _loop
# ---------------------------------------------------------------------------


class TestSchedulerLoop:
    """Test CronScheduler._loop() behavior."""

    @pytest.mark.asyncio
    async def test_loop_stops_when_running_is_false(self) -> None:
        scheduler = CronScheduler()
        scheduler._running = True

        tick_count = 0

        async def counting_tick() -> None:
            nonlocal tick_count
            tick_count += 1
            scheduler._running = False  # stop after first tick

        with (
            patch.object(scheduler, "_tick", side_effect=counting_tick),
            patch("aegra_api.services.cron_scheduler.settings") as mock_settings,
        ):
            mock_settings.cron.CRON_POLL_INTERVAL_SECONDS = 0.01
            await scheduler._loop()

        assert tick_count == 1

    @pytest.mark.asyncio
    async def test_loop_handles_cancelled_error(self) -> None:
        scheduler = CronScheduler()
        scheduler._running = True

        async def raise_cancelled() -> None:
            raise asyncio.CancelledError

        with (
            patch.object(scheduler, "_tick", side_effect=raise_cancelled),
            patch("aegra_api.services.cron_scheduler.settings") as mock_settings,
        ):
            mock_settings.cron.CRON_POLL_INTERVAL_SECONDS = 0.01
            # Should exit cleanly
            await scheduler._loop()

    @pytest.mark.asyncio
    async def test_loop_handles_cancelled_error_during_sleep(self) -> None:
        """CancelledError raised during asyncio.sleep must not kill the loop silently."""
        scheduler = CronScheduler()
        scheduler._running = True

        call_count = 0
        original_sleep = asyncio.sleep

        async def cancelling_sleep(delay: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await original_sleep(delay)
                return
            # Second sleep: simulate external cancellation
            raise asyncio.CancelledError

        with (
            patch.object(scheduler, "_tick", new_callable=AsyncMock),
            patch("aegra_api.services.cron_scheduler.settings") as mock_settings,
            patch("aegra_api.services.cron_scheduler.asyncio.sleep", side_effect=cancelling_sleep),
        ):
            mock_settings.cron.CRON_POLL_INTERVAL_SECONDS = 0.01
            # Should exit cleanly without propagating CancelledError
            await scheduler._loop()

    @pytest.mark.asyncio
    async def test_loop_survives_generic_exception(self) -> None:
        scheduler = CronScheduler()
        scheduler._running = True

        call_count = 0

        async def failing_tick() -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                scheduler._running = False
                return
            raise ValueError("unexpected error")

        with (
            patch.object(scheduler, "_tick", side_effect=failing_tick),
            patch("aegra_api.services.cron_scheduler.settings") as mock_settings,
        ):
            mock_settings.cron.CRON_POLL_INTERVAL_SECONDS = 0.01
            await scheduler._loop()

        assert call_count == 2
