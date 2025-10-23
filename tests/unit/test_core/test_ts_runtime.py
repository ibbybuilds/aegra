"""Unit tests for TypeScript runtime."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agent_server.core.ts_runtime import TypeScriptRuntime


class TestTypeScriptRuntime:
    """Unit tests for TypeScript runtime."""

    @pytest.mark.asyncio
    async def test_missing_node_runtime(self):
        """Test error when no JavaScript runtime is available."""
        runtime = TypeScriptRuntime()

        with (
            patch.object(runtime, "_check_runtime_available", return_value=False),
            pytest.raises(RuntimeError, match="No JavaScript runtime found"),
        ):
            await runtime.initialize()

    @pytest.mark.asyncio
    async def test_runtime_preference_env_var_node(self):
        """Test JS_RUNTIME=node environment variable."""
        runtime = TypeScriptRuntime()

        with (
            patch.dict("os.environ", {"JS_RUNTIME": "node"}),
            patch.object(runtime, "_check_runtime_available", return_value=True),
        ):
            await runtime.initialize()
            assert runtime._runtime_cmd == ["node"]

    @pytest.mark.asyncio
    async def test_runtime_preference_env_var_bun(self):
        """Test JS_RUNTIME=bun environment variable."""
        runtime = TypeScriptRuntime()

        with (
            patch.dict("os.environ", {"JS_RUNTIME": "bun"}),
            patch.object(runtime, "_check_runtime_available", return_value=True),
        ):
            await runtime.initialize()
            assert runtime._runtime_cmd == ["bun", "run"]

    @pytest.mark.asyncio
    async def test_runtime_auto_detect_prefers_bun(self):
        """Test auto-detection prefers bun over node."""
        runtime = TypeScriptRuntime()

        async def check_runtime(name):
            return name == "bun"

        with (
            patch.dict("os.environ", {"JS_RUNTIME": "auto"}),
            patch.object(
                runtime, "_check_runtime_available", side_effect=check_runtime
            ),
        ):
            await runtime.initialize()
            assert runtime._runtime_cmd == ["bun", "run"]

    @pytest.mark.asyncio
    async def test_runtime_auto_detect_fallback_to_node(self):
        """Test auto-detection falls back to node if bun unavailable."""
        runtime = TypeScriptRuntime()

        async def check_runtime(name):
            return name == "node"

        with (
            patch.dict("os.environ", {"JS_RUNTIME": "auto"}),
            patch.object(
                runtime, "_check_runtime_available", side_effect=check_runtime
            ),
        ):
            await runtime.initialize()
            assert runtime._runtime_cmd == ["node"]

    @pytest.mark.asyncio
    async def test_runtime_not_initialized_error(self):
        """Test error when runtime used before initialization."""
        runtime = TypeScriptRuntime()

        with pytest.raises(RuntimeError, match="not initialized"):
            async for _ in runtime._run_node_process("test", {}):
                pass

    def test_json_serialization_check_primitives(self):
        """Test JSON serialization check for primitive types."""
        runtime = TypeScriptRuntime()

        # Should pass
        assert runtime._is_json_serializable(None)
        assert runtime._is_json_serializable(True)
        assert runtime._is_json_serializable(False)
        assert runtime._is_json_serializable(42)
        assert runtime._is_json_serializable(3.14)
        assert runtime._is_json_serializable("hello")

    def test_json_serialization_check_collections(self):
        """Test JSON serialization check for collections."""
        runtime = TypeScriptRuntime()

        # Should pass
        assert runtime._is_json_serializable([1, 2, 3])
        assert runtime._is_json_serializable({"key": "value"})
        assert runtime._is_json_serializable([1, "two", {"three": 3}])
        assert runtime._is_json_serializable({"nested": {"dict": True}})

    def test_json_serialization_check_non_serializable(self):
        """Test JSON serialization check rejects non-serializable types."""
        runtime = TypeScriptRuntime()

        # Should fail
        assert not runtime._is_json_serializable(lambda: None)
        assert not runtime._is_json_serializable(object())
        assert not runtime._is_json_serializable(datetime.now())
        assert not runtime._is_json_serializable({"func": lambda: None})
        assert not runtime._is_json_serializable([1, lambda: None])

    def test_validate_graph_path_missing_file(self):
        """Test validation fails for missing file."""
        runtime = TypeScriptRuntime()

        with pytest.raises(FileNotFoundError, match="not found"):
            runtime._validate_graph_path("/nonexistent/file.ts", "graph")

    def test_validate_graph_path_invalid_extension(self):
        """Test validation fails for invalid extension."""
        runtime = TypeScriptRuntime()

        # Create a temporary Python file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"# python file")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid.*extension"):
                runtime._validate_graph_path(temp_path, "graph")
        finally:
            Path(temp_path).unlink()

    def test_validate_graph_path_invalid_export_name(self):
        """Test validation fails for invalid export name."""
        runtime = TypeScriptRuntime()

        # Create a temporary TypeScript file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
            f.write(b"// typescript file")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid export name"):
                runtime._validate_graph_path(temp_path, "123invalid")

            with pytest.raises(ValueError, match="Invalid export name"):
                runtime._validate_graph_path(temp_path, "")

            with pytest.raises(ValueError, match="Invalid export name"):
                runtime._validate_graph_path(temp_path, "my-export")
        finally:
            Path(temp_path).unlink()

    def test_validate_graph_path_success(self):
        """Test validation succeeds for valid inputs."""
        runtime = TypeScriptRuntime()

        # Create a temporary TypeScript file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
            f.write(b"export const graph = {};")
            temp_path = f.name

        try:
            result = runtime._validate_graph_path(temp_path, "graph")
            assert isinstance(result, Path)
            assert result.exists()
            assert result.suffix == ".ts"
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_malformed_json_in_stream(self):
        """Test handling of malformed JSON in output stream."""
        runtime = TypeScriptRuntime()
        runtime._runtime_cmd = ["echo"]

        # Create mock process with mixed output
        mock_stdout = AsyncMock()
        mock_stdout.__aiter__.return_value = [
            b'{"valid": "json"}\n',
            b"this is not json\n",
            b'{"another": "valid"}\n',
        ]

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            events = []
            async for event in runtime._run_node_process("test", {}):
                events.append(event)

        # Should get 2 valid events, skip the malformed one
        assert len(events) == 2
        assert events[0] == {"valid": "json"}
        assert events[1] == {"another": "valid"}

    @pytest.mark.asyncio
    async def test_graph_execution_failure(self):
        """Test handling of TypeScript graph execution failure."""
        runtime = TypeScriptRuntime()
        runtime._runtime_cmd = ["node"]

        # Mock failed process
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = []
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"Error: module not found")
        mock_process.wait = AsyncMock()
        mock_process.returncode = 1

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            pytest.raises(RuntimeError, match="TypeScript graph execution failed"),
        ):
            async for _ in runtime._run_node_process("test", {}):
                pass

    @pytest.mark.asyncio
    async def test_database_url_conversion(self):
        """Test database URL conversion from asyncpg to psycopg format."""
        runtime = TypeScriptRuntime()

        # Test asyncpg URL conversion
        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db"},
        ):
            url = await runtime._get_database_url()
            assert url == "postgresql://user:pass@localhost:5432/db"

        # Test plain postgresql URL (no conversion)
        with patch.dict(
            "os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost:5432/db"}
        ):
            url = await runtime._get_database_url()
            assert url == "postgresql://user:pass@localhost:5432/db"
