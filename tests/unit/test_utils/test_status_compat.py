"""Tests for status validation utilities."""

import pytest

from agent_server.utils.status_compat import (
    validate_run_status,
    validate_thread_status,
)


class TestValidateRunStatus:
    """Tests for run status validation."""

    def test_validate_standard_statuses(self):
        """Test that standard statuses are accepted."""
        standard_statuses = [
            "pending",
            "running",
            "error",
            "success",
            "timeout",
            "interrupted",
        ]
        for status in standard_statuses:
            assert validate_run_status(status) == status

    def test_reject_invalid_status(self):
        """Test that invalid statuses raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run status"):
            validate_run_status("invalid_status")

    def test_reject_legacy_statuses(self):
        """Test that legacy statuses are rejected (migration handles conversion)."""
        legacy_statuses = ["completed", "failed", "cancelled"]
        for status in legacy_statuses:
            with pytest.raises(ValueError, match="Invalid run status"):
                validate_run_status(status)


class TestValidateThreadStatus:
    """Tests for thread status validation."""

    def test_validate_standard_thread_statuses(self):
        """Test that standard thread statuses are accepted."""
        valid_statuses = ["idle", "busy", "interrupted", "error"]
        for status in valid_statuses:
            assert validate_thread_status(status) == status

    def test_reject_invalid_thread_status(self):
        """Test that invalid thread statuses raise ValueError."""
        with pytest.raises(ValueError, match="Invalid thread status"):
            validate_thread_status("invalid_status")
