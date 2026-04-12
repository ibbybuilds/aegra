"""Tests for aegra_api.utils.setup_logging.

Regression tests for #295 and the full logging processor chain audit.
Ensures the shared processor chain includes all required processors
in the correct order for both dev and production modes.
"""

import json
import logging
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import structlog

from aegra_api.utils.setup_logging import get_logging_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_config(*, env_mode: str, log_level: str = "INFO") -> dict:
    """Get logging config with mocked settings."""
    with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
        mock_settings.app.ENV_MODE = env_mode
        mock_settings.app.LOG_LEVEL = log_level
        return get_logging_config()


def _get_pre_chain(config: dict) -> list:
    """Extract the foreign_pre_chain from a logging config."""
    return config["formatters"]["default"]["foreign_pre_chain"]


def _make_capturing_logger(config: dict, name: str) -> tuple[logging.Logger, list[str]]:
    """Create a stdlib logger that captures formatted output into a list."""
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=config["formatters"]["default"]["processors"],
        foreign_pre_chain=config["formatters"]["default"]["foreign_pre_chain"],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    records: list[str] = []
    handler.emit = lambda record: records.append(formatter.format(record))  # type: ignore[assignment]

    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, records


# ---------------------------------------------------------------------------
# Production mode (JSONRenderer)
# ---------------------------------------------------------------------------


class TestProcessorChainProduction:
    """Tests for production mode processor chain."""

    def test_format_exc_info_present(self) -> None:
        """format_exc_info must be present so JSONRenderer includes
        tracebacks in production log output (#295)."""
        pre_chain = _get_pre_chain(_get_config(env_mode="PRODUCTION"))
        assert structlog.processors.format_exc_info in pre_chain

    def test_uses_json_renderer(self) -> None:
        config = _get_config(env_mode="PRODUCTION")
        processors = config["formatters"]["default"]["processors"]
        assert isinstance(processors[-1], structlog.processors.JSONRenderer)

    def test_format_exc_info_before_positional_args(self) -> None:
        """format_exc_info should appear before PositionalArgumentsFormatter.

        There is no strict dependency between them (they operate on different
        event dict keys), but this ordering reflects the intended declaration
        order in setup_logging.py.
        """
        pre_chain = _get_pre_chain(_get_config(env_mode="PRODUCTION"))

        exc_info_idx = pre_chain.index(structlog.processors.format_exc_info)
        pos_args_idx = next(
            i for i, p in enumerate(pre_chain) if isinstance(p, structlog.stdlib.PositionalArgumentsFormatter)
        )
        assert exc_info_idx < pos_args_idx


# ---------------------------------------------------------------------------
# Dev mode (ConsoleRenderer)
# ---------------------------------------------------------------------------


class TestProcessorChainDev:
    """Tests for LOCAL/DEVELOPMENT mode processor chain."""

    @pytest.mark.parametrize("env_mode", ["LOCAL", "DEVELOPMENT"])
    def test_format_exc_info_absent(self, env_mode: str) -> None:
        """format_exc_info must NOT be in dev mode so ConsoleRenderer's
        exception_formatter can render pretty tracebacks."""
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert structlog.processors.format_exc_info not in pre_chain

    @pytest.mark.parametrize("env_mode", ["LOCAL", "DEVELOPMENT"])
    def test_uses_console_renderer(self, env_mode: str) -> None:
        config = _get_config(env_mode=env_mode)
        processors = config["formatters"]["default"]["processors"]
        assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)


# ---------------------------------------------------------------------------
# Shared processors (present in ALL modes)
# ---------------------------------------------------------------------------


class TestSharedProcessorsCommon:
    """Tests for processors that must be present in all modes."""

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_merge_contextvars_is_first(self, env_mode: str) -> None:
        """merge_contextvars must be the first processor so request-scoped
        context (request_id, run_id, etc.) is available to all others."""
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert pre_chain[0] is structlog.contextvars.merge_contextvars

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_stack_info_renderer_present(self, env_mode: str) -> None:
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert any(isinstance(p, structlog.processors.StackInfoRenderer) for p in pre_chain)

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_unicode_decoder_present(self, env_mode: str) -> None:
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert any(isinstance(p, structlog.processors.UnicodeDecoder) for p in pre_chain)

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_extra_adder_present(self, env_mode: str) -> None:
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert any(isinstance(p, structlog.stdlib.ExtraAdder) for p in pre_chain)

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_timestamper_present(self, env_mode: str) -> None:
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert any(isinstance(p, structlog.processors.TimeStamper) for p in pre_chain)

    @pytest.mark.parametrize("env_mode", ["LOCAL", "PRODUCTION"])
    def test_callsite_parameter_adder_present(self, env_mode: str) -> None:
        pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
        assert any(isinstance(p, structlog.processors.CallsiteParameterAdder) for p in pre_chain)


# ---------------------------------------------------------------------------
# ProcessorFormatter configuration
# ---------------------------------------------------------------------------


class TestProcessorFormatterConfig:
    """Tests for the ProcessorFormatter configuration."""

    def test_uses_processors_list_not_singular(self) -> None:
        """Must use 'processors' (plural) with remove_processors_meta,
        not the legacy 'processor' (singular) parameter."""
        config = _get_config(env_mode="PRODUCTION")
        formatter_config = config["formatters"]["default"]
        assert "processors" in formatter_config
        assert "processor" not in formatter_config

    def test_remove_processors_meta_before_renderer(self) -> None:
        config = _get_config(env_mode="PRODUCTION")
        processors = config["formatters"]["default"]["processors"]
        assert processors[0] is structlog.stdlib.ProcessorFormatter.remove_processors_meta

    def test_disable_existing_loggers_false(self) -> None:
        config = _get_config(env_mode="PRODUCTION")
        assert config["disable_existing_loggers"] is False


# ---------------------------------------------------------------------------
# Processor ordering
# ---------------------------------------------------------------------------


class TestProcessorOrdering:
    """Tests for the correct ordering of all processors."""

    def test_full_production_order(self) -> None:
        """Verify the complete processor ordering for production mode."""
        pre_chain = _get_pre_chain(_get_config(env_mode="PRODUCTION"))

        def find_idx(target: type | object) -> int:
            for i, p in enumerate(pre_chain):
                if p is target:
                    return i
                if isinstance(target, type) and isinstance(p, target):
                    return i
            raise AssertionError(f"{target} not found in pre_chain")

        merge_idx = find_idx(structlog.contextvars.merge_contextvars)
        level_idx = find_idx(structlog.stdlib.add_log_level)
        stack_idx = find_idx(structlog.processors.StackInfoRenderer)
        exc_idx = pre_chain.index(structlog.processors.format_exc_info)
        pos_idx = find_idx(structlog.stdlib.PositionalArgumentsFormatter)
        unicode_idx = find_idx(structlog.processors.UnicodeDecoder)

        assert merge_idx < level_idx, "merge_contextvars must come before enrichment"
        assert stack_idx < exc_idx, "StackInfoRenderer must come before format_exc_info"
        assert exc_idx < pos_idx, "format_exc_info should come before PositionalArgumentsFormatter (convention)"
        assert pos_idx < unicode_idx, "PositionalArgumentsFormatter must come before UnicodeDecoder"


# ---------------------------------------------------------------------------
# Runtime integration (end-to-end through the real pipeline)
# ---------------------------------------------------------------------------


class TestRuntimeOutput:
    """End-to-end tests that exercise the full processor pipeline and verify
    actual rendered output, not just processor chain configuration."""

    @pytest.fixture(autouse=True)
    def _reset_structlog(self) -> Iterator[None]:
        """Restore structlog config after tests that call structlog.configure."""
        old_config = structlog.get_config()
        yield
        structlog.configure(**old_config)

    def test_production_json_contains_traceback(self) -> None:
        """Regression test for #295: JSONRenderer must include the full
        traceback text, not just 'exc_info: true'."""
        config = _get_config(env_mode="PRODUCTION")
        logger, records = _make_capturing_logger(config, "test.runtime.traceback")

        try:
            raise ValueError("test error for regression #295")
        except ValueError:
            logger.exception("Something failed")

        assert len(records) == 1
        parsed = json.loads(records[0])
        assert "exception" in parsed, "JSON output must contain 'exception' field"
        assert "Traceback" in parsed["exception"]
        assert "ValueError" in parsed["exception"]
        assert "test error for regression #295" in parsed["exception"]

    def test_production_json_contains_context_vars(self) -> None:
        """merge_contextvars must propagate bound context into JSON output."""
        config = _get_config(env_mode="PRODUCTION")

        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                *config["formatters"]["default"]["foreign_pre_chain"],
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=False,
        )

        _, records = _make_capturing_logger(config, "test.runtime.contextvars")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="test-req-123", user_id="alice")

        logger = structlog.stdlib.get_logger("test.runtime.contextvars")
        logger.info("request processed", status_code=200)

        structlog.contextvars.clear_contextvars()

        assert len(records) == 1
        parsed = json.loads(records[0])
        assert parsed["request_id"] == "test-req-123"
        assert parsed["user_id"] == "alice"
        assert parsed["status_code"] == 200
