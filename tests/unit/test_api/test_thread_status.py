"""Tests for thread status API functions."""

from unittest.mock import AsyncMock, patch

import pytest

from agent_server.api.runs import set_thread_status


class TestSetThreadStatus:
    """Tests for set_thread_status function."""

    @pytest.mark.asyncio
    async def test_set_thread_status_validates_status(self):
        """Test that set_thread_status validates status before updating."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        # Valid status should work
        await set_thread_status(session, "thread-123", "busy")
        session.execute.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_thread_status_rejects_invalid_status(self):
        """Test that set_thread_status rejects invalid status values."""
        session = AsyncMock()

        with pytest.raises(ValueError, match="Invalid thread status"):
            await set_thread_status(session, "thread-123", "invalid_status")

        # Should not execute or commit with invalid status
        session.execute.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_thread_status_all_valid_statuses(self):
        """Test that set_thread_status accepts all valid statuses."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        valid_statuses = ["idle", "busy", "interrupted", "error"]
        for status in valid_statuses:
            session.reset_mock()
            await set_thread_status(session, "thread-123", status)
            session.execute.assert_called_once()
            session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_thread_status_imports_validation(self):
        """Test that set_thread_status imports and uses validation."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        # Patch validate_thread_status in the utils module to verify it's called
        with patch(
            "agent_server.utils.status_compat.validate_thread_status"
        ) as mock_validate:
            mock_validate.return_value = "busy"
            await set_thread_status(session, "thread-123", "busy")
            mock_validate.assert_called_once_with("busy")
