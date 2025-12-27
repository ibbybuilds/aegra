"""LangGraph integration service with official patterns"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid5

import structlog
from langgraph.graph import StateGraph
from langgraph.pregel import Pregel

from ..constants import ASSISTANT_NAMESPACE_UUID
from ..observability.base import get_tracing_callbacks, get_tracing_metadata

State = TypeVar("State")
logger = structlog.get_logger(__name__)


class LangGraphService:
    """Service to work with LangGraph CLI configuration and graphs"""

    def __init__(self, config_path: str = "aegra.json"):
        # Default path can be overridden via AEGRA_CONFIG or by placing aegra.json
        self.config_path = Path(config_path)
        self.config: dict[str, Any] | None = None
        self._graph_registry: dict[str, Any] = {}
        self._graph_cache: dict[str, Any] = {}

    async def initialize(self):
        """Load configuration file and setup graph registry.

        Uses shared config loading logic to ensure consistency.
        Resolution order:
        1) AEGRA_CONFIG env var (absolute or relative path)
        2) Explicit self.config_path if it exists
        3) aegra.json in CWD
        4) langgraph.json in CWD (fallback)
        """
        from ..config import _resolve_config_path

        # Priority: env var > explicit config_path > shared resolution
        resolved_path: Path | None = None

        # 1) Check env var first (via shared resolution logic)
        env_resolved = _resolve_config_path()

        # 2) If env var was set, use it (even if file doesn't exist yet - let error happen later)
        env_path = os.getenv("AEGRA_CONFIG")
        if env_path and env_resolved and env_resolved == Path(env_path):
            resolved_path = env_resolved
        # 3) Otherwise check explicit config_path (if provided and exists)
        elif self.config_path and Path(self.config_path).exists():
            resolved_path = Path(self.config_path)
        # 4) Otherwise use shared resolution (fallback to aegra.json/langgraph.json)
        else:
            resolved_path = env_resolved

        if not resolved_path or not resolved_path.exists():
            raise ValueError(
                "Configuration file not found. Expected one of: "
                "AEGRA_CONFIG path, ./aegra.json, or ./langgraph.json"
            )

        # Persist selected path for later reference
        self.config_path = resolved_path

        with self.config_path.open() as f:
            self.config = json.load(f)

        # Setup dependency paths before loading graphs
        self._setup_dependencies()

        # Load graph registry from config
        self._load_graph_registry()

        # Pre-register assistants for each graph using deterministic UUIDs so
        # clients can pass graph_id directly.
        await self._ensure_default_assistants()

    def _load_graph_registry(self):
        """Load graph definitions from aegra.json"""
        graphs_config = self.config.get("graphs", {})

        for graph_id, graph_path in graphs_config.items():
            # Parse path format: "./graphs/weather_agent.py:graph"
            if ":" not in graph_path:
                raise ValueError(f"Invalid graph path format: {graph_path}")

            file_path, export_name = graph_path.split(":", 1)
            self._graph_registry[graph_id] = {
                "file_path": file_path,
                "export_name": export_name,
            }

    def _setup_dependencies(self) -> None:
        """Add dependency paths to sys.path for graph imports.

        Supports paths from the 'dependencies' config key, similar to LangGraph CLI.
        Paths are resolved relative to the config file location.
        """
        dependencies = self.config.get("dependencies", [])
        if not dependencies:
            return

        config_dir = self.config_path.parent

        # Iterate in reverse so first dependency in config has highest priority
        for dep in reversed(dependencies):
            dep_path = Path(dep)

            # Resolve relative paths from config directory
            if not dep_path.is_absolute():
                dep_path = (config_dir / dep_path).resolve()
            else:
                dep_path = dep_path.resolve()

            # Add to sys.path if exists and not already present
            path_str = str(dep_path)
            if dep_path.exists() and path_str not in sys.path:
                sys.path.insert(0, path_str)
                logger.info(f"Added dependency path to sys.path: {path_str}")
            elif not dep_path.exists():
                logger.warning(f"Dependency path does not exist: {path_str}")

    async def _ensure_default_assistants(self) -> None:
        """Create a default assistant per graph with deterministic UUID.

        Uses uuid5 with a fixed namespace so that the same graph_id maps
        to the same assistant_id across restarts. Idempotent.
        """
        from sqlalchemy import select

        from ..core.orm import Assistant as AssistantORM
        from ..core.orm import AssistantVersion as AssistantVersionORM
        from ..core.orm import get_session

        # Fixed namespace used to derive assistant IDs from graph IDs
        NS = ASSISTANT_NAMESPACE_UUID
        session_gen = get_session()
        session = await anext(session_gen)
        try:
            for graph_id in self._graph_registry:
                assistant_id = str(uuid5(NS, graph_id))
                existing = await session.scalar(
                    select(AssistantORM).where(
                        AssistantORM.assistant_id == assistant_id
                    )
                )
                if existing:
                    continue
                session.add(
                    AssistantORM(
                        assistant_id=assistant_id,
                        name=graph_id,
                        description=f"Default assistant for graph '{graph_id}'",
                        graph_id=graph_id,
                        config={},
                        user_id="system",
                        metadata_dict={"created_by": "system"},
                    )
                )
                session.add(
                    AssistantVersionORM(
                        assistant_id=assistant_id,
                        version=1,
                        name=graph_id,
                        description=f"Default assistant for graph '{graph_id}'",
                        graph_id=graph_id,
                        metadata_dict={"created_by": "system"},
                    )
                )
            await session.commit()
        finally:
            await session.close()

    async def get_graph(self, graph_id: str, force_reload: bool = False) -> Pregel:
        """Get a compiled graph by ID with caching and LangGraph integration"""
        if graph_id not in self._graph_registry:
            raise ValueError(f"Graph not found: {graph_id}")

        # Return cached graph if available and not forcing reload
        if not force_reload and graph_id in self._graph_cache:
            return self._graph_cache[graph_id]

        graph_info = self._graph_registry[graph_id]

        # Load graph from file
        base_graph = await self._load_graph_from_file(graph_id, graph_info)

        # Always ensure graphs are compiled with our Postgres checkpointer for persistence
        from ..core.database import db_manager

        checkpointer_cm = db_manager.get_checkpointer()
        store_cm = db_manager.get_store()

        if isinstance(base_graph, StateGraph):
            # The module exported an *uncompiled* StateGraph – compile it now with
            # a Postgres checkpointer for durable state.

            logger.info(f"🔧 Compiling graph '{graph_id}' with Postgres persistence")
            compiled_graph = base_graph.compile(
                checkpointer=checkpointer_cm, store=store_cm
            )
        else:
            # Graph was already compiled by the module.  Create a shallow copy
            # that injects our Postgres checkpointer *unless* the author already
            # set one.
            try:
                compiled_graph = base_graph.copy(
                    update={"checkpointer": checkpointer_cm, "store": store_cm}
                )
            except Exception:
                # Fallback: property may be immutably set; run as-is with warning
                logger.warning(
                    f"⚠️  Pre-compiled graph '{graph_id}' does not support checkpointer injection; running without persistence"
                )
                compiled_graph = base_graph

        # Cache the compiled graph
        self._graph_cache[graph_id] = compiled_graph

        return compiled_graph

    async def _load_graph_from_file(self, graph_id: str, graph_info: dict[str, str]):
        """Load graph from filesystem"""
        file_path = Path(graph_info["file_path"])
        if not file_path.exists():
            raise ValueError(f"Graph file not found: {file_path}")

        # Dynamic import of graph module
        spec = importlib.util.spec_from_file_location(
            f"graphs.{graph_id}", str(file_path.resolve())
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load graph module: {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get the exported graph
        export_name = graph_info["export_name"]
        if not hasattr(module, export_name):
            raise ValueError(f"Graph export not found: {export_name} in {file_path}")

        graph = getattr(module, export_name)

        # https://github.com/langchain-ai/langchain-mcp-adapters?tab=readme-ov-file#using-with-langgraph-api-server
        if callable(graph):
            graph = await graph()

        # The graph should already be compiled in the module
        # If it needs our checkpointer/store, we'll handle that during execution
        return graph

    def list_graphs(self) -> dict[str, str]:
        """List all available graphs"""
        return {
            graph_id: info["file_path"]
            for graph_id, info in self._graph_registry.items()
        }

    def invalidate_cache(self, graph_id: str = None):
        """Invalidate graph cache for hot-reload"""
        if graph_id:
            self._graph_cache.pop(graph_id, None)
        else:
            self._graph_cache.clear()

    def get_config(self) -> dict[str, Any] | None:
        """Get loaded configuration"""
        return self.config

    def get_dependencies(self) -> list:
        """Get dependencies from config"""
        if self.config is None:
            return []
        return self.config.get("dependencies", [])

    def get_http_config(self) -> dict[str, Any] | None:
        """Get HTTP configuration from loaded config file.

        Returns:
            HTTP configuration dict or None if not configured
        """
        if self.config is None:
            return None
        return self.config.get("http")


# Global service instance
_langgraph_service = None


def get_langgraph_service() -> LangGraphService:
    """Get global LangGraph service instance"""
    global _langgraph_service
    if _langgraph_service is None:
        _langgraph_service = LangGraphService()
    return _langgraph_service


def inject_user_context(user, base_config: dict = None) -> dict:
    """Inject user context into LangGraph configuration for user isolation"""
    config = (base_config or {}).copy()
    config["configurable"] = config.get("configurable", {})

    # All user-related data injection (only if user exists)
    if user:
        # Basic user identity for multi-tenant scoping
        config["configurable"].setdefault("user_id", user.identity)
        config["configurable"].setdefault(
            "user_display_name", getattr(user, "display_name", user.identity)
        )

        # Full auth payload for graph nodes
        if "langgraph_auth_user" not in config["configurable"]:
            try:
                config["configurable"]["langgraph_auth_user"] = user.to_dict()  # type: ignore[attr-defined]
            except Exception:
                # Fallback: minimal dict if to_dict unavailable
                config["configurable"]["langgraph_auth_user"] = {
                    "identity": user.identity
                }

    return config


def create_thread_config(thread_id: str, user, additional_config: dict = None) -> dict:
    """Create LangGraph configuration for a specific thread with user context"""
    base_config = {"configurable": {"thread_id": thread_id}}

    if additional_config:
        base_config.update(additional_config)

    return inject_user_context(user, base_config)


def create_run_config(
    run_id: str,
    thread_id: str,
    user,
    additional_config: dict = None,
    checkpoint: dict | None = None,
) -> dict:
    """Create LangGraph configuration for a specific run with full context.

    The function is *additive*: it never removes or renames anything the client
    supplied.  We simply ensure a `configurable` dict exists and then merge a
    few server-side keys so graph nodes can rely on them.
    """
    from copy import deepcopy

    cfg: dict = deepcopy(additional_config) if additional_config else {}

    # Ensure a configurable section exists
    cfg.setdefault("configurable", {})

    # Merge server-provided fields (do NOT overwrite if client already set)
    cfg["configurable"].setdefault("thread_id", thread_id)
    cfg["configurable"].setdefault("run_id", run_id)

    # Add observability callbacks from various potential sources
    tracing_callbacks = get_tracing_callbacks()
    if tracing_callbacks:
        existing_callbacks = cfg.get("callbacks", [])
        if not isinstance(existing_callbacks, list):
            # If we want to be more robust, we can log a warning here
            existing_callbacks = []

        # Combine existing callbacks with new tracing callbacks to be non-destructive
        cfg["callbacks"] = existing_callbacks + tracing_callbacks

    # Add metadata from all observability providers (independent of callbacks)
    cfg.setdefault("metadata", {})
    user_identity = user.identity if user else None
    observability_metadata = get_tracing_metadata(run_id, thread_id, user_identity)
    cfg["metadata"].update(observability_metadata)

    # Apply checkpoint parameters if provided
    if checkpoint and isinstance(checkpoint, dict):
        cfg["configurable"].update(
            {k: v for k, v in checkpoint.items() if v is not None}
        )

    # Finally inject user context via existing helper
    return inject_user_context(user, cfg)
