"""Unit tests for AssistantService schema extraction logic

These tests focus on the schema extraction helper functions.
"""

from unittest.mock import Mock

import pytest

from agent_server.services.assistant_service import (
    _extract_graph_schemas,
    _get_configurable_jsonschema,
    _state_jsonschema,
)


class TestStateJsonSchema:
    """Test state JSON schema extraction"""

    def test_state_jsonschema_success(self):
        """Test successful state schema extraction"""
        # Mock graph with channels
        mock_graph = Mock()
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "TestState"

        result = _state_jsonschema(mock_graph)

        assert result is not None
        assert "properties" in result

    def test_state_jsonschema_exception_handling(self):
        """Test state schema extraction with exceptions"""
        # Mock graph that raises exception during create_model
        mock_graph = Mock()
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "TestState"

        # Mock create_model to raise exception
        with pytest.MonkeyPatch().context() as mp:

            def mock_create_model(*args, **kwargs):
                raise Exception("Schema error")

            mp.setattr("langchain_core.runnables.utils.create_model", mock_create_model)

            # The function doesn't have try-catch, so it will raise the exception
            with pytest.raises(Exception) as exc_info:
                _state_jsonschema(mock_graph)

            assert "Schema error" in str(exc_info.value)

    def test_state_jsonschema_empty_channels(self):
        """Test state schema extraction with empty channels"""
        mock_graph = Mock()
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "EmptyState"

        result = _state_jsonschema(mock_graph)

        assert result is not None
        assert "properties" in result
        assert len(result["properties"]) == 0


class TestConfigurableJsonSchema:
    """Test configurable JSON schema extraction"""

    def test_get_configurable_jsonschema_success(self):
        """Test successful configurable schema extraction"""
        # Mock graph with config schema
        mock_graph = Mock()
        mock_config_schema = Mock()
        mock_config_schema.model_fields = {"configurable": Mock(annotation=dict)}

        mock_graph.config_schema.return_value = mock_config_schema
        mock_graph.config_type = Mock()
        mock_graph.config_type.__name__ = "TestConfig"

        # Mock TypeAdapter to return a proper schema
        with pytest.MonkeyPatch().context() as mp:
            mock_adapter = Mock()
            mock_adapter.json_schema.return_value = {
                "properties": {"key": {"type": "string"}},
                "title": "TestConfig",
            }
            mp.setattr("pydantic.TypeAdapter", lambda x: mock_adapter)

            result = _get_configurable_jsonschema(mock_graph)

            assert result is not None
            assert "title" in result
            assert result["title"] == "TestConfig"

    def test_get_configurable_jsonschema_no_configurable(self):
        """Test configurable schema extraction without configurable field"""
        mock_graph = Mock()
        mock_config_schema = Mock()
        mock_config_schema.model_fields = {"other_field": Mock()}

        mock_graph.config_schema.return_value = mock_config_schema

        result = _get_configurable_jsonschema(mock_graph)

        assert result == {}

    def test_get_configurable_jsonschema_no_model_fields(self):
        """Test configurable schema extraction without model_fields"""
        mock_graph = Mock()
        mock_config_schema = Mock()
        mock_config_schema.model_fields = None
        mock_config_schema.__fields__ = None

        mock_graph.config_schema.return_value = mock_config_schema

        result = _get_configurable_jsonschema(mock_graph)

        assert result == {}

    def test_get_configurable_jsonschema_excluded_keys(self):
        """Test configurable schema extraction with excluded keys"""
        mock_graph = Mock()
        mock_config_schema = Mock()
        mock_config_schema.model_fields = {"configurable": Mock(annotation=dict)}

        mock_graph.config_schema.return_value = mock_config_schema
        mock_graph.config_type = None

        # Mock the TypeAdapter to return schema with excluded keys
        with pytest.MonkeyPatch().context() as mp:
            mock_adapter = Mock()
            mock_adapter.json_schema.return_value = {
                "properties": {
                    "__pregel_resuming": {"type": "boolean"},
                    "__pregel_checkpoint_id": {"type": "string"},
                    "valid_key": {"type": "string"},
                }
            }
            mp.setattr("pydantic.TypeAdapter", lambda x: mock_adapter)

            result = _get_configurable_jsonschema(mock_graph)

            assert result is not None
            assert "__pregel_resuming" not in result["properties"]
            assert "__pregel_checkpoint_id" not in result["properties"]
            assert "valid_key" in result["properties"]

    def test_get_configurable_jsonschema_exception_handling(self):
        """Test configurable schema extraction with exceptions"""
        mock_graph = Mock()
        mock_graph.config_schema.side_effect = Exception("Config error")

        # The function doesn't have try-catch, so it will raise the exception
        with pytest.raises(Exception) as exc_info:
            _get_configurable_jsonschema(mock_graph)

        assert "Config error" in str(exc_info.value)


class TestExtractGraphSchemas:
    """Test graph schema extraction"""

    def test_extract_graph_schemas_success(self):
        """Test successful graph schema extraction"""
        # Mock graph with all schema methods
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.return_value = {"type": "object", "input": True}
        mock_graph.get_output_jsonschema.return_value = {
            "type": "object",
            "output": True,
        }
        mock_graph.get_context_jsonschema.return_value = {
            "type": "object",
            "context": True,
        }

        # Mock state schema extraction
        mock_graph.stream_channels_list = ["messages"]
        mock_graph.channels = {"messages": Mock()}
        mock_graph.get_name.return_value = "State"

        # Mock config schema
        mock_graph.config_schema.return_value = Mock()
        mock_graph.config_schema.return_value.model_fields = {
            "configurable": Mock(annotation=dict)
        }
        mock_graph.config_type = Mock()
        mock_graph.config_type.__name__ = "TestConfig"

        result = _extract_graph_schemas(mock_graph)

        assert "input_schema" in result
        assert "output_schema" in result
        assert "state_schema" in result
        assert "config_schema" in result
        assert "context_schema" in result

        assert result["input_schema"]["input"] is True
        assert result["output_schema"]["output"] is True
        assert result["context_schema"]["context"] is True

    def test_extract_graph_schemas_partial_failure(self):
        """Test graph schema extraction with partial failures"""
        # Mock graph with some failing methods
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.return_value = {"type": "object"}
        mock_graph.get_output_jsonschema.side_effect = Exception("Output error")
        mock_graph.get_context_jsonschema.side_effect = Exception("Context error")

        # Mock state schema failure
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.side_effect = Exception("State error")

        # Mock config schema failure
        mock_graph.config_schema.side_effect = Exception("Config error")

        result = _extract_graph_schemas(mock_graph)

        assert "input_schema" in result
        assert result["input_schema"] is not None
        assert result["output_schema"] is None
        assert result["state_schema"] is None
        assert result["config_schema"] is None
        assert result["context_schema"] is None

    def test_extract_graph_schemas_all_failures(self):
        """Test graph schema extraction with all failures"""
        # Mock graph with all failing methods
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.side_effect = Exception("Input error")
        mock_graph.get_output_jsonschema.side_effect = Exception("Output error")
        mock_graph.get_context_jsonschema.side_effect = Exception("Context error")

        # Mock state schema failure
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.side_effect = Exception("State error")

        # Mock config schema failure
        mock_graph.config_schema.side_effect = Exception("Config error")

        result = _extract_graph_schemas(mock_graph)

        assert "input_schema" in result
        assert "output_schema" in result
        assert "state_schema" in result
        assert "config_schema" in result
        assert "context_schema" in result

        # All should be None due to failures
        assert result["input_schema"] is None
        assert result["output_schema"] is None
        assert result["state_schema"] is None
        assert result["config_schema"] is None
        assert result["context_schema"] is None

    def test_extract_graph_schemas_complex_state(self):
        """Test graph schema extraction with complex state"""
        # Mock graph with complex state
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.return_value = {"type": "object"}
        mock_graph.get_output_jsonschema.return_value = {"type": "object"}
        mock_graph.get_context_jsonschema.return_value = {"type": "object"}

        # Mock complex state with multiple channels
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "ComplexState"

        # Mock config schema
        mock_graph.config_schema.return_value = Mock()
        mock_graph.config_schema.return_value.model_fields = {
            "configurable": Mock(annotation=dict)
        }
        mock_graph.config_type = Mock()
        mock_graph.config_type.__name__ = "ComplexConfig"

        # Mock TypeAdapter
        with pytest.MonkeyPatch().context() as mp:
            mock_adapter = Mock()
            mock_adapter.json_schema.return_value = {
                "properties": {"key": {"type": "string"}},
                "title": "ComplexConfig",
            }
            mp.setattr("pydantic.TypeAdapter", lambda x: mock_adapter)

            result = _extract_graph_schemas(mock_graph)

            assert "state_schema" in result
            assert result["state_schema"] is not None
            assert "properties" in result["state_schema"]

    def test_extract_graph_schemas_empty_graph(self):
        """Test graph schema extraction with empty graph"""
        # Mock empty graph
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.return_value = {}
        mock_graph.get_output_jsonschema.return_value = {}
        mock_graph.get_context_jsonschema.return_value = {}

        # Mock empty state
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "EmptyState"

        # Mock empty config
        mock_graph.config_schema.return_value = Mock()
        mock_graph.config_schema.return_value.model_fields = {}
        mock_graph.config_type = None

        result = _extract_graph_schemas(mock_graph)

        assert "input_schema" in result
        assert "output_schema" in result
        assert "state_schema" in result
        assert "config_schema" in result
        assert "context_schema" in result

        # All should be empty but not None
        assert result["input_schema"] == {}
        assert result["output_schema"] == {}
        assert result["context_schema"] == {}
        assert result["config_schema"] == {}
