"""Tests for aegra_api.utils.setup_logging.

Regression tests for #295 and the full logging processor chain audit.
Ensures the shared processor chain includes all required processors
in the correct order for both dev and production modes.
"""

import json
import logging
from unittest.mock import patch

import structlog

from aegra_api.utils.setup_logging import get_logging_config


def _get_config(*, env_mode: str, log_level: str = "INFO") -> dict:
    """Helper to get logging config with mocked settings."""
    with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
        mock_settings.app.ENV_MODE = env_mode
        mock_settings.app.LOG_LEVEL = log_level
        return get_logging_config()


def _get_pre_chain(config: dict) -> list:
    """Extract the foreign_pre_chain from a logging config."""
    return config["formatters"]["default"]["foreign_pre_chain"]


class TestProcessorChainProduction:
    """Tests for production mode (JSONRenderer) processor chain."""

    def test_format_exc_info_present(self) -> None:
        """format_exc_info must be in shared_processors so JSONRenderer
        includes tracebacks in production log output (#295)."""
        pre_chain = _get_pre_chain(_get_config(env_mode="PRODUCTION"))
        assert structlog.processors.format_exc_info in pre_chain

    def test_uses_json_renderer(self) -> None:
        """Production mode must use JSONRenderer."""
        config = _get_config(env_mode="PRODUCTION")
        processors = config["formatters"]["default"]["processors"]
        # Last processor is the renderer
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


class TestProcessorChainDev:
    """Tests for LOCAL/DEVELOPMENT mode (ConsoleRenderer) processor chain."""

    def test_format_exc_info_absent(self) -> None:
        """format_exc_info must NOT be in dev mode so ConsoleRenderer's
        RichTracebackFormatter can render pretty exceptions."""
        pre_chain = _get_pre_chain(_get_config(env_mode="LOCAL"))
        assert structlog.processors.format_exc_info not in pre_chain

    def test_format_exc_info_absent_development(self) -> None:
        """Same check for DEVELOPMENT mode."""
        pre_chain = _get_pre_chain(_get_config(env_mode="DEVELOPMENT"))
        assert structlog.processors.format_exc_info not in pre_chain

    def test_uses_console_renderer(self) -> None:
        """LOCAL mode must use ConsoleRenderer."""
        config = _get_config(env_mode="LOCAL")
        processors = config["formatters"]["default"]["processors"]
        assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)


class TestSharedProcessorsCommon:
    """Tests for processors that must be present in ALL modes."""

    def test_merge_contextvars_is_first(self) -> None:
        """merge_contextvars must be the first processor so request-scoped
        context (request_id, run_id, etc.) is available to all others."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert pre_chain[0] is structlog.contextvars.merge_contextvars, (
                f"merge_contextvars must be first in {env_mode} mode"
            )

    def test_stack_info_renderer_present(self) -> None:
        """StackInfoRenderer must be present so stack_info=True in log
        calls actually renders the stack trace."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert any(isinstance(p, structlog.processors.StackInfoRenderer) for p in pre_chain), (
                f"StackInfoRenderer missing in {env_mode} mode"
            )

    def test_unicode_decoder_present(self) -> None:
        """UnicodeDecoder must be present to handle byte strings from
        third-party libraries."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert any(isinstance(p, structlog.processors.UnicodeDecoder) for p in pre_chain), (
                f"UnicodeDecoder missing in {env_mode} mode"
            )

    def test_extra_adder_present(self) -> None:
        """ExtraAdder must be present so stdlib extra={} kwargs are
        captured in structured output."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert any(isinstance(p, structlog.stdlib.ExtraAdder) for p in pre_chain), (
                f"ExtraAdder missing in {env_mode} mode"
            )

    def test_timestamper_present(self) -> None:
        """TimeStamper must be present for ISO timestamps."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert any(isinstance(p, structlog.processors.TimeStamper) for p in pre_chain), (
                f"TimeStamper missing in {env_mode} mode"
            )

    def test_callsite_parameter_adder_present(self) -> None:
        """CallsiteParameterAdder must be present for filename, func, lineno."""
        for env_mode in ("LOCAL", "PRODUCTION"):
            pre_chain = _get_pre_chain(_get_config(env_mode=env_mode))
            assert any(isinstance(p, structlog.processors.CallsiteParameterAdder) for p in pre_chain), (
                f"CallsiteParameterAdder missing in {env_mode} mode"
            )


class TestProcessorFormatterConfig:
    """Tests for the ProcessorFormatter configuration."""

    def test_uses_processors_list_not_singular(self) -> None:
        """Must use 'processors' (plural) with remove_processors_meta,
        not the legacy 'processor' (singular) parameter."""
        config = _get_config(env_mode="PRODUCTION")
        formatter_config = config["formatters"]["default"]
        assert "processors" in formatter_config, "Should use 'processors' (plural), not legacy 'processor' (singular)"
        assert "processor" not in formatter_config

    def test_remove_processors_meta_before_renderer(self) -> None:
        """remove_processors_meta must come before the renderer."""
        config = _get_config(env_mode="PRODUCTION")
        processors = config["formatters"]["default"]["processors"]
        assert processors[0] is structlog.stdlib.ProcessorFormatter.remove_processors_meta

    def test_disable_existing_loggers_false(self) -> None:
        """disable_existing_loggers must be False to keep library loggers."""
        config = _get_config(env_mode="PRODUCTION")
        assert config["disable_existing_loggers"] is False


class TestProcessorOrdering:
    """Tests for the correct ordering of all processors."""

    def test_full_production_order(self) -> None:
        """Verify the complete processor ordering for production mode."""
        pre_chain = _get_pre_chain(_get_config(env_mode="PRODUCTION"))

        # Build a map of processor to index. Handles both plain functions
        # (identity check) and class instances (isinstance check).
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

        # merge_contextvars < enrichment < stack_info < format_exc_info < pos_args < unicode
        assert merge_idx < level_idx, "merge_contextvars must come before enrichment"
        assert stack_idx < exc_idx, "StackInfoRenderer must come before format_exc_info"
        assert exc_idx < pos_idx, "format_exc_info should come before PositionalArgumentsFormatter (convention)"
        assert pos_idx < unicode_idx, "PositionalArgumentsFormatter must come before UnicodeDecoder"


class TestRuntimeOutput:
    """End-to-end tests that exercise the full processor pipeline and verify
    actual rendered output, not just processor chain configuration."""

    def test_production_json_contains_traceback(self) -> None:
        """Regression test for #295: JSONRenderer must include the full
        traceback text in the rendered output, not just 'exc_info: true'."""
        config = _get_config(env_mode="PRODUCTION")
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=config["formatters"]["default"]["processors"],
            foreign_pre_chain=config["formatters"]["default"]["foreign_pre_chain"],
        )

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        test_logger = logging.getLogger("test.runtime.production")
        test_logger.handlers = [handler]
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False

        # Capture the formatted output via the handler
        records: list[str] = []
        original_emit = handler.emit

        def capturing_emit(record: logging.LogRecord) -> None:
            records.append(formatter.format(record))

        handler.emit = capturing_emit  # type: ignore[assignment]

        try:
            raise ValueError("test error for regression #295")
        except ValueError:
            test_logger.exception("Something failed")

        handler.emit = original_emit  # type: ignore[assignment]

        assert len(records) == 1
        parsed = json.loads(records[0])
        assert "exception" in parsed, "JSON output must contain 'exception' field"
        assert "Traceback" in parsed["exception"]
        assert "ValueError" in parsed["exception"]
        assert "test error for regression #295" in parsed["exception"]

    def test_production_json_contains_context_vars(self) -> None:
        """merge_contextvars must propagate bound context into JSON output."""
        config = _get_config(env_mode="PRODUCTION")

        # Configure structlog with the production pipeline
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

        formatter = structlog.stdlib.ProcessorFormatter(
            processors=config["formatters"]["default"]["processors"],
            foreign_pre_chain=config["formatters"]["default"]["foreign_pre_chain"],
        )

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        # Attach to the underlying stdlib logger that structlog will use
        stdlib_logger = logging.getLogger("test.runtime.contextvars")
        stdlib_logger.handlers = [handler]
        stdlib_logger.setLevel(logging.DEBUG)
        stdlib_logger.propagate = False

        records: list[str] = []
        original_emit = handler.emit

        def capturing_emit(record: logging.LogRecord) -> None:
            records.append(formatter.format(record))

        handler.emit = capturing_emit  # type: ignore[assignment]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="test-req-123", user_id="alice")

        logger = structlog.stdlib.get_logger("test.runtime.contextvars")
        logger.info("request processed", status_code=200)

        structlog.contextvars.clear_contextvars()
        handler.emit = original_emit  # type: ignore[assignment]

        assert len(records) == 1
        parsed = json.loads(records[0])
        assert parsed["request_id"] == "test-req-123"
        assert parsed["user_id"] == "alice"
        assert parsed["status_code"] == 200
