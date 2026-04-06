"""Tests for aegra_api.utils.setup_logging.

Regression test for #295: structlog JSONRenderer was dropping exception
tracebacks in production mode because format_exc_info was missing from
the shared processor chain.
"""

from unittest.mock import patch

import structlog

from aegra_api.utils.setup_logging import get_logging_config


class TestGetLoggingConfig:
    """Tests for the get_logging_config function."""

    def test_shared_processors_include_format_exc_info_production(self) -> None:
        """format_exc_info must be in shared_processors so JSONRenderer
        includes tracebacks in production log output (#295)."""
        with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
            mock_settings.app.ENV_MODE = "PRODUCTION"
            mock_settings.app.LOG_LEVEL = "INFO"

            config = get_logging_config()

        pre_chain = config["formatters"]["default"]["foreign_pre_chain"]
        assert structlog.processors.format_exc_info in pre_chain

    def test_shared_processors_include_format_exc_info_local(self) -> None:
        """format_exc_info should also be present in LOCAL mode for
        consistency, even though ConsoleRenderer handles it internally."""
        with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
            mock_settings.app.ENV_MODE = "LOCAL"
            mock_settings.app.LOG_LEVEL = "DEBUG"

            config = get_logging_config()

        pre_chain = config["formatters"]["default"]["foreign_pre_chain"]
        assert structlog.processors.format_exc_info in pre_chain

    def test_production_uses_json_renderer(self) -> None:
        """Production mode must use JSONRenderer, not ConsoleRenderer."""
        with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
            mock_settings.app.ENV_MODE = "PRODUCTION"
            mock_settings.app.LOG_LEVEL = "INFO"

            config = get_logging_config()

        renderer = config["formatters"]["default"]["processor"]
        assert isinstance(renderer, structlog.processors.JSONRenderer)

    def test_local_uses_console_renderer(self) -> None:
        """LOCAL mode must use ConsoleRenderer."""
        with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
            mock_settings.app.ENV_MODE = "LOCAL"
            mock_settings.app.LOG_LEVEL = "DEBUG"

            config = get_logging_config()

        renderer = config["formatters"]["default"]["processor"]
        assert isinstance(renderer, structlog.dev.ConsoleRenderer)

    def test_format_exc_info_before_positional_args_formatter(self) -> None:
        """format_exc_info must run before PositionalArgumentsFormatter
        so that exception text is available when positional args are formatted."""
        with patch("aegra_api.utils.setup_logging.settings") as mock_settings:
            mock_settings.app.ENV_MODE = "PRODUCTION"
            mock_settings.app.LOG_LEVEL = "INFO"

            config = get_logging_config()

        pre_chain = config["formatters"]["default"]["foreign_pre_chain"]

        exc_info_idx = pre_chain.index(structlog.processors.format_exc_info)
        pos_args_idx = next(
            i
            for i, p in enumerate(pre_chain)
            if isinstance(p, structlog.stdlib.PositionalArgumentsFormatter)
        )
        assert exc_info_idx < pos_args_idx, (
            "format_exc_info must come before PositionalArgumentsFormatter"
        )
