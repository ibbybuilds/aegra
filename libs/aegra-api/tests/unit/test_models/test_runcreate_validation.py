"""Tests for RunCreate model validation."""

import pytest

from aegra_api.models.runs import RunCreate


class TestRunCreateValidation:
    """Tests for RunCreate input/command validation."""

    def test_allows_checkpoint_only_payload(self):
        """Ensure checkpoint-only payloads are accepted and default input to empty dict."""
        run_create = RunCreate(
            assistant_id="agent",
            checkpoint={"checkpoint_id": "chk-1", "checkpoint_ns": ""},
        )

        assert run_create.input == {}
        assert run_create.command is None

    def test_rejects_payload_without_input_command_or_checkpoint(self):
        """Ensure payloads with no input, command, or checkpoint are rejected."""
        with pytest.raises(ValueError, match="Must specify either 'input' or 'command'"):
            RunCreate(assistant_id="agent")
