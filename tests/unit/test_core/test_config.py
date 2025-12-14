"""Unit tests for HTTP configuration loading"""

import json

from src.agent_server.config import load_http_config


def test_load_http_config_from_aegra_json(tmp_path, monkeypatch):
    """Test loading HTTP config from aegra.json"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create aegra.json with http config
    config_file = tmp_path / "aegra.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {
                    "app": "./custom.py:app",
                    "enable_custom_route_auth": True,
                },
            }
        )
    )

    config = load_http_config()

    assert config is not None
    assert config["app"] == "./custom.py:app"
    assert config["enable_custom_route_auth"] is True


def test_load_http_config_from_langgraph_json(tmp_path, monkeypatch):
    """Test loading HTTP config from langgraph.json fallback"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create langgraph.json with http config (no aegra.json)
    config_file = tmp_path / "langgraph.json"
    config_file.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {
                    "app": "./custom.py:app",
                },
            }
        )
    )

    config = load_http_config()

    assert config is not None
    assert config["app"] == "./custom.py:app"


def test_load_http_config_prefers_aegra_json(tmp_path, monkeypatch):
    """Test that aegra.json takes precedence over langgraph.json"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create both config files
    aegra_config = tmp_path / "aegra.json"
    aegra_config.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {"app": "./aegra_custom.py:app"},
            }
        )
    )

    langgraph_config = tmp_path / "langgraph.json"
    langgraph_config.write_text(
        json.dumps(
            {
                "graphs": {"test": "./test.py:graph"},
                "http": {"app": "./langgraph_custom.py:app"},
            }
        )
    )

    config = load_http_config()

    assert config is not None
    assert config["app"] == "./aegra_custom.py:app"


def test_load_http_config_no_config(tmp_path, monkeypatch):
    """Test loading when no config file exists"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    config = load_http_config()

    assert config is None


def test_load_http_config_no_http_section(tmp_path, monkeypatch):
    """Test loading when config exists but no http section"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "aegra.json"
    config_file.write_text(json.dumps({"graphs": {"test": "./test.py:graph"}}))

    config = load_http_config()

    assert config is None


def test_load_http_config_invalid_json(tmp_path, monkeypatch):
    """Test loading when config file has invalid JSON"""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "aegra.json"
    config_file.write_text("{ invalid json }")

    # Should return None and log warning
    config = load_http_config()

    assert config is None
