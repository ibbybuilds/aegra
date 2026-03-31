"""Tests for A2A/MCP config fields in HttpConfig."""

import json
from pathlib import Path
from unittest.mock import patch

from aegra_api.config import HttpConfig, load_http_config


def test_http_config_accepts_disable_a2a() -> None:
    """HttpConfig TypedDict allows disable_a2a field."""
    config: HttpConfig = {"disable_a2a": True}
    assert config["disable_a2a"] is True


def test_http_config_accepts_disable_mcp() -> None:
    """HttpConfig TypedDict allows disable_mcp field."""
    config: HttpConfig = {"disable_mcp": True}
    assert config["disable_mcp"] is True


def test_load_http_config_returns_disable_flags(tmp_path: Path) -> None:
    """load_http_config returns disable_a2a and disable_mcp from aegra.json."""
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {},
                "http": {"disable_a2a": True, "disable_mcp": False},
            }
        )
    )
    with patch("aegra_api.config._resolve_config_path", return_value=config_file):
        result = load_http_config()

    assert result is not None
    assert result["disable_a2a"] is True
    assert result["disable_mcp"] is False


def test_load_http_config_defaults_when_flags_absent(tmp_path: Path) -> None:
    """When disable_a2a/disable_mcp are absent, they default to False via .get()."""
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps({"graphs": {}, "http": {"enable_custom_route_auth": False}})
    )
    with patch("aegra_api.config._resolve_config_path", return_value=config_file):
        result = load_http_config()

    assert result is not None
    assert result.get("disable_a2a", False) is False
    assert result.get("disable_mcp", False) is False
