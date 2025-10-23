"""TypeScript runtime manager for executing TypeScript/JavaScript graphs.

This module handles spawning and managing Node.js processes for TypeScript graphs,
providing IPC communication and lifecycle management.
"""

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Configuration keys that cannot be serialized to JSON for TypeScript graphs
# These are typically Python-specific objects like callbacks or tracing handlers
NON_SERIALIZABLE_CONFIG_KEYS = ["callbacks", "tags", "metadata"]

# Configuration keys that should always be passed through
# These are required by LangGraph for state management and execution control
REQUIRED_CONFIG_KEYS = ["configurable"]

# Supported TypeScript/JavaScript file extensions
SUPPORTED_TS_EXTENSIONS = {".ts", ".mts", ".cts", ".js", ".mjs", ".cjs"}


class TypeScriptRuntime:
    """Manager for TypeScript graph execution via Node.js processes."""

    def __init__(self, node_version: str = "20"):
        """Initialize TypeScript runtime manager.

        Args:
            node_version: Node.js version to use
        """
        self.node_version = node_version
        self._runtime_cmd: list[str] | None = None

    async def initialize(self):
        """Initialize runtime and detect available JavaScript runtime."""
        self._runtime_cmd = await self._detect_runtime_command()
        logger.info("Using JavaScript runtime: %s", " ".join(self._runtime_cmd))

    async def execute_graph(
        self,
        graph_id: str,
        graph_path: str,
        export_name: str,
        input_data: dict[str, Any],
        config: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute a TypeScript graph and stream results.

        Note: Some config keys are filtered before sending to TypeScript:
        - callbacks: Python callback functions (not serializable)
        - tags: Used for tracing (handled separately)
        - metadata: May contain non-serializable objects

        The 'configurable' key is always preserved as it contains essential
        runtime configuration like thread_id, checkpoint_ns, etc.

        Args:
            graph_id: Graph identifier
            graph_path: Path to TypeScript file
            export_name: Name of exported graph variable
            input_data: Input data for the graph
            config: Configuration including thread_id, run_id, etc.

        Yields:
            Graph execution events
        """
        # Validate inputs early
        validated_path = self._validate_graph_path(graph_path, export_name)

        # Filter config to only include JSON-serializable values
        serializable_config = {
            k: v
            for k, v in config.items()
            if k not in NON_SERIALIZABLE_CONFIG_KEYS and self._is_json_serializable(v)
        }

        # Always preserve required config keys
        for key in REQUIRED_CONFIG_KEYS:
            if key in config:
                serializable_config[key] = config[key]

        # Prepare execution context
        execution_context = {
            "graph_path": str(validated_path),
            "export_name": export_name,
            "input": input_data,
            "config": serializable_config,
            "database_url": await self._get_database_url(),
        }

        # Execute via Node.js wrapper
        async for event in self._run_node_process(graph_id, execution_context):
            yield event

    def _validate_graph_path(self, graph_path: str, export_name: str) -> Path:
        """Validate TypeScript graph path and export name.

        Args:
            graph_path: Path to the graph file
            export_name: Name of the exported graph variable

        Returns:
            Resolved absolute path to the graph file

        Raises:
            FileNotFoundError: If graph file doesn't exist
            ValueError: If file extension is not supported or export name is invalid
        """
        graph_file = Path(graph_path).resolve()

        if not graph_file.exists():
            raise FileNotFoundError(
                f"TypeScript graph file not found: {graph_file}\n"
                f"Current working directory: {Path.cwd()}"
            )

        if graph_file.suffix not in SUPPORTED_TS_EXTENSIONS:
            raise ValueError(
                f"Invalid TypeScript graph file extension: {graph_file.suffix}\n"
                f"Supported extensions: {', '.join(sorted(SUPPORTED_TS_EXTENSIONS))}"
            )

        if not export_name or not export_name.isidentifier():
            raise ValueError(
                f"Invalid export name: '{export_name}'\n"
                f"Export name must be a valid JavaScript identifier"
            )

        return graph_file

    def _is_json_serializable(self, obj: Any) -> bool:
        """Check if an object is JSON serializable without actually serializing it.

        This is a fast path check that avoids the overhead of json.dumps().
        Only basic Python types are considered serializable for TypeScript graphs.
        """
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return True

        if isinstance(obj, (list, tuple)):
            return all(self._is_json_serializable(item) for item in obj)

        if isinstance(obj, dict):
            return all(
                isinstance(k, str) and self._is_json_serializable(v)
                for k, v in obj.items()
            )

        # Reject everything else (functions, classes, etc.)
        return False

    async def _get_database_url(self) -> str:
        """Get PostgreSQL connection URL for TypeScript graphs.

        TypeScript graphs use the same PostgreSQL checkpointer as Python graphs.
        """
        asyncpg_url = os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/aegra"
        )

        # Convert postgresql+asyncpg:// to postgresql://
        if asyncpg_url.startswith("postgresql+asyncpg://"):
            postgres_url = asyncpg_url.replace("postgresql+asyncpg://", "postgresql://")
        else:
            postgres_url = asyncpg_url

        return postgres_url

    async def _run_node_process(
        self, graph_id: str, context: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Run Node.js process and handle IPC communication.

        Args:
            graph_id: Graph identifier (for logging/debugging)
            context: Execution context with graph path, input, config, etc.

        Yields:
            Execution events from the TypeScript graph
        """
        if self._runtime_cmd is None:
            raise RuntimeError(
                "TypeScriptRuntime not initialized. Call initialize() first."
            )

        logger.debug("Executing TypeScript graph: %s", graph_id)

        # Create a wrapper script that will be executed by Node.js
        wrapper_script = self._generate_wrapper_script()

        # Write context to temporary file for IPC
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(context, f)
            context_file = f.name

        try:
            # Spawn Node.js/bun process
            process = await asyncio.create_subprocess_exec(
                *self._runtime_cmd,
                wrapper_script,
                context_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream output
            if process.stdout:
                async for line in process.stdout:
                    decoded_line = line.decode().strip()
                    try:
                        event = json.loads(decoded_line)
                        yield event
                    except json.JSONDecodeError:
                        logger.warning(
                            "Non-JSON output from TS graph %s: %s",
                            graph_id,
                            decoded_line,
                        )
                        continue

            # Wait for process to complete
            await process.wait()

            if process.returncode != 0 and process.stderr:
                stderr = await process.stderr.read()
                logger.error(
                    "TypeScript graph %s execution failed: %s",
                    graph_id,
                    stderr.decode(),
                )
                raise RuntimeError(
                    f"TypeScript graph execution failed: {stderr.decode()}"
                )

        finally:
            # Cleanup temporary file
            with contextlib.suppress(Exception):
                Path(context_file).unlink()

    async def _detect_runtime_command(self) -> list[str]:
        """Detect which JavaScript runtime to use (cached result).

        Returns:
            Command to run JavaScript runtime

        Raises:
            RuntimeError: If no suitable runtime is found or specified runtime unavailable
        """
        # Check environment variable first
        runtime_pref = os.getenv("JS_RUNTIME", "auto").lower()

        if runtime_pref == "node":
            if await self._check_runtime_available("node"):
                return ["node"]
            raise RuntimeError("JS_RUNTIME=node specified but node not found")

        if runtime_pref == "bun":
            if await self._check_runtime_available("bun"):
                return ["bun", "run"]
            raise RuntimeError("JS_RUNTIME=bun specified but bun not found")

        # Auto-detect: prefer bun, fallback to node
        if await self._check_runtime_available("bun"):
            return ["bun", "run"]

        if await self._check_runtime_available("node"):
            return ["node"]

        raise RuntimeError(
            "No JavaScript runtime found. Please install Node.js >= 20 or bun. "
            "Set JS_RUNTIME=node or JS_RUNTIME=bun to specify preference."
        )

    async def _check_runtime_available(self, runtime: str) -> bool:
        """Check if a runtime is available.

        Args:
            runtime: Runtime name (e.g., 'node', 'bun')

        Returns:
            True if runtime is available, False otherwise
        """
        try:
            process = await asyncio.create_subprocess_exec(
                runtime,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()
            return process.returncode == 0
        except FileNotFoundError:
            return False

    def _generate_wrapper_script(self) -> str:
        """Generate a Node.js wrapper script for executing TypeScript graphs.

        This script:
        1. Reads execution context from a JSON file
        2. Loads the TypeScript graph
        3. Executes it with the provided input and config
        4. Streams results back via stdout

        Returns:
            Path to the wrapper script
        """
        # Use the TypeScript wrapper - Bun can run .ts files directly
        wrapper_path = Path(__file__).parent / "ts_graph_wrapper.ts"
        if not wrapper_path.exists():
            raise RuntimeError(
                f"TypeScript graph wrapper not found: {wrapper_path}. "
                "This file should be created to handle TS graph execution."
            )
        return str(wrapper_path)
