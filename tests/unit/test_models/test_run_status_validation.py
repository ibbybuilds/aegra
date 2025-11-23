"""Tests for Run model status validation."""

from datetime import UTC, datetime

import pytest

from agent_server.models.runs import Run


class TestRunStatusValidation:
    """Tests for Run model status field validation."""

    def test_run_validates_standard_statuses(self):
        """Test that Run model accepts standard statuses."""
        standard_statuses = [
            "pending",
            "running",
            "error",
            "success",
            "timeout",
            "interrupted",
        ]
        for status in standard_statuses:
            run = Run(
                run_id=f"test-run-{status}",
                thread_id="test-thread-1",
                assistant_id="test-assistant-1",
                status=status,
                input={},
                user_id="test-user",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            assert run.status == status

    def test_run_rejects_invalid_status(self):
        """Test that Run model rejects invalid status values."""
        with pytest.raises(ValueError, match="Invalid run status"):
            Run(
                run_id="test-run-1",
                thread_id="test-thread-1",
                assistant_id="test-assistant-1",
                status="invalid_status",
                input={},
                user_id="test-user",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    def test_run_rejects_legacy_statuses(self):
        """Test that Run model rejects legacy statuses (migration handles conversion)."""
        legacy_statuses = ["completed", "failed", "cancelled"]
        for status in legacy_statuses:
            with pytest.raises(ValueError, match="Invalid run status"):
                Run(
                    run_id=f"test-run-{status}",
                    thread_id="test-thread-1",
                    assistant_id="test-assistant-1",
                    status=status,
                    input={},
                    user_id="test-user",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

    def test_run_from_orm_with_standard_status(self):
        """Test that Run model accepts standard statuses from ORM."""

        # Simulate ORM object with standard status
        class MockORM:
            run_id = "test-run-1"
            thread_id = "test-thread-1"
            assistant_id = "test-assistant-1"
            status = "success"  # Standard status
            input = {}
            output = None
            error_message = None
            config = {}
            context = {}
            user_id = "test-user"
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        run = Run.model_validate(MockORM())
        assert run.status == "success"
