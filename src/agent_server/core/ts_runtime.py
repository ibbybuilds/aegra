"""TypeScript runtime manager for executing TypeScript/JavaScript graphs.

This module handles spawning and managing Node.js processes for TypeScript graphs,
providing IPC communication and lifecycle management.
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator
import sys

from ..core.database import db_manager


class TypeScriptRuntime:
    """Manager for TypeScript graph execution via Node.js processes."""

    def __init__(self, node_version: str = "20"):
        """Initialize TypeScript runtime manager.

        Args:
            node_version: Node.js version to use
        """
        self.node_version = node_version
        self._process_pool: dict[str, subprocess.Popen] = {}

    async def execute_graph(
        self,
        graph_id: str,
        graph_path: str,
        export_name: str,
        input_data: dict[str, Any],
        config: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute a TypeScript graph and stream results.

        Args:
            graph_id: Graph identifier
            graph_path: Path to TypeScript file
            export_name: Name of exported graph variable
            input_data: Input data for the graph
            config: Configuration including thread_id, run_id, etc.

        Yields:
            Graph execution events
        """
        # Prepare execution context
        execution_context = {
            "graph_path": str(Path(graph_path).resolve()),
            "export_name": export_name,
            "input": input_data,
            "config": config,
            "database_url": await self._get_database_url(),
        }

        # Execute via Node.js wrapper
        async for event in self._run_node_process(graph_id, execution_context):
            yield event

    async def _get_database_url(self) -> str:
        """Get PostgreSQL connection URL for TypeScript graphs.

        TypeScript graphs use the same PostgreSQL checkpointer as Python graphs.
        """
        # Convert asyncpg URL to standard PostgreSQL URL for langgraph-checkpoint-postgres
        from ..core.database import db_manager

        asyncpg_url = db_manager.database_url

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
            graph_id: Graph identifier
            context: Execution context

        Yields:
            Execution events from the TypeScript graph
        """
        # Create a wrapper script that will be executed by Node.js
        wrapper_script = self._generate_wrapper_script()

        # Write context to temporary file for IPC
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(context, f)
            context_file = f.name

        try:
            # Check if Node.js/bun is available
            runtime_cmd = await self._get_runtime_command()

            # Spawn Node.js/bun process
            process = await asyncio.create_subprocess_exec(
                *runtime_cmd,
                wrapper_script,
                context_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream output
            if process.stdout:
                async for line in process.stdout:
                    try:
                        event = json.loads(line.decode().strip())
                        yield event
                    except json.JSONDecodeError as e:
                        # Log non-JSON output (debugging info, etc.)
                        print(f"Non-JSON output from TS graph: {line.decode().strip()}")
                        continue

            # Wait for process to complete
            await process.wait()

            if process.returncode != 0 and process.stderr:
                stderr = await process.stderr.read()
                raise RuntimeError(
                    f"TypeScript graph execution failed: {stderr.decode()}"
                )

        finally:
            # Cleanup temporary file
            try:
                Path(context_file).unlink()
            except Exception:
                pass

    async def _get_runtime_command(self) -> list[str]:
        """Determine which JavaScript runtime to use (bun or node).

        Returns:
            Command to run JavaScript runtime

        Raises:
            RuntimeError: If no suitable runtime is found
        """
        # Prefer bun if available
        try:
            result = await asyncio.create_subprocess_exec(
                "bun", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.wait()
            if result.returncode == 0:
                return ["bun", "run"]
        except FileNotFoundError:
            pass

        # Fall back to node
        try:
            result = await asyncio.create_subprocess_exec(
                "node", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.wait()
            if result.returncode == 0:
                return ["node"]
        except FileNotFoundError:
            pass

        raise RuntimeError(
            "No JavaScript runtime found. Please install Node.js >= 20 or bun."
        )

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
        # For now, return a placeholder path
        # TODO: Implement the actual wrapper script
        # This will be a separate TypeScript/JavaScript file that:
        # - Uses @langchain/langgraph to load and execute the graph
        # - Connects to PostgreSQL using the provided URL
        # - Streams execution events as JSON lines

        wrapper_path = Path(__file__).parent / "ts_graph_wrapper.js"
        if not wrapper_path.exists():
            raise RuntimeError(
                f"TypeScript graph wrapper not found: {wrapper_path}. "
                "This file should be created to handle TS graph execution."
            )
        return str(wrapper_path)

    async def shutdown(self):
        """Shutdown all running Node.js processes."""
        for graph_id, process in self._process_pool.items():
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception as e:
                print(f"Error terminating process for graph {graph_id}: {e}")
                try:
                    process.kill()
                except Exception:
                    pass

        self._process_pool.clear()


# Global runtime instance
_ts_runtime: TypeScriptRuntime | None = None


def get_ts_runtime(node_version: str = "20") -> TypeScriptRuntime:
    """Get global TypeScript runtime instance.

    Args:
        node_version: Node.js version to use

    Returns:
        TypeScript runtime instance
    """
    global _ts_runtime
    if _ts_runtime is None:
        _ts_runtime = TypeScriptRuntime(node_version)
    return _ts_runtime
