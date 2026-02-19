"""Unit tests for graph factory support (Runtime and RunnableConfig factories)."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from aegra_api.services.graph_factory import (
    GraphFactory,
    Runtime,
    build_default_context,
    coerce_context,
    extract_context_schema,
)
from aegra_api.services.langgraph_service import LangGraphService


class TestCoerceContext:
    """Tests for coerce_context helper."""

    def test_coerce_context_none_context(self) -> None:
        """None context passes through regardless of schema."""

        class MyModel(BaseModel):
            name: str

        result = coerce_context(MyModel, None)
        assert result is None

    def test_coerce_context_none_schema(self) -> None:
        """None schema passes through the dict unchanged."""
        ctx = {"name": "test"}
        result = coerce_context(None, ctx)
        assert result == {"name": "test"}

    def test_coerce_context_pydantic(self) -> None:
        """Dict is coerced to a Pydantic model when schema is a BaseModel subclass."""

        class UserContext(BaseModel):
            user_id: str
            role: str

        result = coerce_context(UserContext, {"user_id": "u1", "role": "admin"})
        assert isinstance(result, UserContext)
        assert result.user_id == "u1"
        assert result.role == "admin"

    def test_coerce_context_dataclass(self) -> None:
        """Dict is coerced to a dataclass when schema is a dataclass type."""

        @dataclass
        class Settings:
            model: str
            temperature: float

        result = coerce_context(Settings, {"model": "gpt-4", "temperature": 0.7})
        assert isinstance(result, Settings)
        assert result.model == "gpt-4"
        assert result.temperature == 0.7

    def test_coerce_context_plain_dict(self) -> None:
        """Non-model, non-dataclass schema returns dict as-is."""
        result = coerce_context(dict, {"key": "value"})
        assert result == {"key": "value"}


class TestExtractContextSchema:
    """Tests for extract_context_schema helper."""

    def test_extract_from_plain_runtime(self) -> None:
        """Plain Runtime (not parameterised) should return None."""

        def factory(runtime: Runtime) -> None: ...

        result = extract_context_schema(factory)
        assert result is None

    def test_extract_no_runtime_param(self) -> None:
        """Returns None when factory has no runtime parameter."""

        def factory(x: int) -> None: ...

        result = extract_context_schema(factory)
        assert result is None

    def test_extract_no_type_hints(self) -> None:
        """Returns None when type hints can't be resolved."""

        def factory(runtime): ...

        result = extract_context_schema(factory)
        assert result is None


class TestBuildDefaultContext:
    """Tests for build_default_context helper."""

    def test_none_schema(self) -> None:
        """None schema returns None."""
        assert build_default_context(None) is None

    def test_pydantic_all_defaults(self) -> None:
        """Pydantic model with all defaults is instantiated."""

        class Ctx(BaseModel):
            name: str = "default"
            temp: float = 0.5

        result = build_default_context(Ctx)
        assert isinstance(result, Ctx)
        assert result.name == "default"
        assert result.temp == 0.5

    def test_dataclass_all_defaults(self) -> None:
        """Dataclass with all defaults is instantiated."""

        @dataclass
        class Ctx:
            name: str = "default"

        result = build_default_context(Ctx)
        assert isinstance(result, Ctx)
        assert result.name == "default"

    def test_pydantic_required_fields_returns_none(self) -> None:
        """Pydantic model with required fields returns None (can't build default)."""

        class Ctx(BaseModel):
            name: str  # required, no default

        result = build_default_context(Ctx)
        assert result is None

    def test_dataclass_required_fields_returns_none(self) -> None:
        """Dataclass with required fields returns None (can't build default)."""

        @dataclass
        class Ctx:
            name: str  # required, no default

        result = build_default_context(Ctx)
        assert result is None


class TestLoadGraphRuntimeFactory:
    """Tests for runtime-aware factory detection in _load_graph_from_file."""

    @pytest.mark.asyncio
    async def test_load_graph_detects_runtime_factory(self) -> None:
        """Callable with `runtime` param returns a GraphFactory wrapper."""
        service = LangGraphService()

        mock_graph = Mock()

        async def make_graph(runtime: Runtime) -> Mock:
            return mock_graph

        mock_module = Mock()
        mock_module.graph = make_graph

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module_from_spec,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()
            mock_module_from_spec.return_value = mock_module

            graph_info = {"file_path": "test.py", "export_name": "graph"}
            result = await service._load_graph_from_file("test_graph", graph_info)

            assert isinstance(result, GraphFactory)
            assert result.factory is make_graph
            assert result.context_schema is None  # No generic param

    @pytest.mark.asyncio
    async def test_load_graph_simple_callable_no_runtime(self) -> None:
        """Callable without `runtime` param is called immediately (existing behavior)."""
        service = LangGraphService()

        mock_graph = object()

        async def simple_factory() -> object:
            return mock_graph

        mock_module = Mock()
        mock_module.graph = simple_factory

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module_from_spec,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()
            mock_module_from_spec.return_value = mock_module

            graph_info = {"file_path": "test.py", "export_name": "graph"}
            result = await service._load_graph_from_file("test_graph", graph_info)

            assert result is mock_graph


class TestGetGraphWithContext:
    """Tests for get_graph with runtime-aware factory context."""

    @pytest.mark.asyncio
    async def test_get_graph_with_context_calls_factory(self) -> None:
        """Factory is called per-request with Runtime when context is provided."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()
        mock_compiled.copy = Mock(return_value=mock_compiled)

        call_log: list[Runtime] = []

        async def make_graph(runtime: Runtime) -> Mock:
            call_log.append(runtime)
            return mock_compiled

        service._graph_factories["test_graph"] = GraphFactory(
            factory=make_graph,
            kind="runtime",
            context_schema=None,
        )

        with patch("aegra_api.core.database.db_manager") as mock_db_manager:
            mock_db_manager.get_checkpointer = Mock(return_value="cp")
            mock_db_manager.get_store = Mock(return_value="st")

            async with service.get_graph("test_graph", context={"key": "val"}) as graph:
                assert graph == mock_compiled

        assert len(call_log) == 1
        assert call_log[0].context == {"key": "val"}

    @pytest.mark.asyncio
    async def test_get_graph_with_context_coerces_pydantic(self) -> None:
        """Factory context is coerced to Pydantic model when schema is set."""

        class MyCtx(BaseModel):
            model_name: str

        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()
        mock_compiled.copy = Mock(return_value=mock_compiled)

        captured_runtime: list[Runtime] = []

        async def make_graph(runtime: Runtime) -> Mock:
            captured_runtime.append(runtime)
            return mock_compiled

        service._graph_factories["test_graph"] = GraphFactory(
            factory=make_graph,
            kind="runtime",
            context_schema=MyCtx,
        )

        with patch("aegra_api.core.database.db_manager") as mock_db_manager:
            mock_db_manager.get_checkpointer = Mock(return_value="cp")
            mock_db_manager.get_store = Mock(return_value="st")

            async with service.get_graph("test_graph", context={"model_name": "gpt-4"}) as _graph:
                pass

        assert isinstance(captured_runtime[0].context, MyCtx)
        assert captured_runtime[0].context.model_name == "gpt-4"

    @pytest.mark.asyncio
    async def test_get_graph_without_context_uses_cached_base(self) -> None:
        """No context falls back to cached base graph even when factory exists."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_base = Mock()
        mock_base.copy = Mock(return_value=mock_base)
        service._base_graph_cache["test_graph"] = mock_base

        factory_called = False

        async def make_graph(runtime: Runtime) -> Mock:
            nonlocal factory_called
            factory_called = True
            return Mock()

        service._graph_factories["test_graph"] = GraphFactory(
            factory=make_graph,
            kind="runtime",
            context_schema=None,
        )

        with patch("aegra_api.core.database.db_manager") as mock_db_manager:
            mock_db_manager.get_checkpointer = Mock(return_value="cp")
            mock_db_manager.get_store = Mock(return_value="st")

            async with service.get_graph("test_graph") as graph:
                assert graph == mock_base

        assert not factory_called

    @pytest.mark.asyncio
    async def test_get_base_graph_registers_factory(self) -> None:
        """_get_base_graph registers factory and calls with default Runtime for base graph."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()

        async def make_graph(runtime: Runtime) -> Mock:
            return mock_compiled

        factory = GraphFactory(factory=make_graph, kind="runtime", context_schema=None)

        with patch.object(service, "_load_graph_from_file", return_value=factory):
            result = await service._get_base_graph("test_graph")

        assert result is mock_compiled
        assert "test_graph" in service._graph_factories
        assert service._graph_factories["test_graph"] is factory
        assert service._base_graph_cache["test_graph"] is mock_compiled

    @pytest.mark.asyncio
    async def test_get_base_graph_passes_default_context_to_factory(self) -> None:
        """When context_schema has all-default fields, factory receives a populated context."""

        class Ctx(BaseModel):
            system_prompt: str = "default prompt"

        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()
        captured_runtimes: list[Runtime] = []

        async def make_graph(runtime: Runtime) -> Mock:
            captured_runtimes.append(runtime)
            return mock_compiled

        factory = GraphFactory(factory=make_graph, kind="runtime", context_schema=Ctx)

        with patch.object(service, "_load_graph_from_file", return_value=factory):
            await service._get_base_graph("test_graph")

        assert len(captured_runtimes) == 1
        assert isinstance(captured_runtimes[0].context, Ctx)
        assert captured_runtimes[0].context.system_prompt == "default prompt"


class TestRunnableConfigFactory:
    """Tests for RunnableConfig-based graph factories."""

    @pytest.mark.asyncio
    async def test_load_graph_detects_config_factory(self) -> None:
        """Callable with `config` param (RunnableConfig) returns a config GraphFactory."""
        service = LangGraphService()

        mock_graph = Mock()

        async def make_graph(config: dict) -> Mock:
            return mock_graph

        mock_module = Mock()
        mock_module.graph = make_graph

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module_from_spec,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()
            mock_module_from_spec.return_value = mock_module

            graph_info = {"file_path": "test.py", "export_name": "graph"}
            result = await service._load_graph_from_file("test_graph", graph_info)

            assert isinstance(result, GraphFactory)
            assert result.kind == "config"
            assert result.factory is make_graph

    @pytest.mark.asyncio
    async def test_get_graph_with_run_config_calls_factory(self) -> None:
        """Config factory is called per-request with run_config when provided."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()
        mock_compiled.copy = Mock(return_value=mock_compiled)

        call_log: list[dict] = []

        async def make_graph(config: dict) -> Mock:
            call_log.append(config)
            return mock_compiled

        service._graph_factories["test_graph"] = GraphFactory(
            factory=make_graph,
            kind="config",
        )

        run_cfg = {"configurable": {"thread_id": "t1", "model": "gpt-4"}}

        with patch("aegra_api.core.database.db_manager") as mock_db_manager:
            mock_db_manager.get_checkpointer = Mock(return_value="cp")
            mock_db_manager.get_store = Mock(return_value="st")

            async with service.get_graph("test_graph", run_config=run_cfg) as graph:
                assert graph == mock_compiled

        assert len(call_log) == 1
        assert call_log[0] == run_cfg

    @pytest.mark.asyncio
    async def test_get_graph_config_factory_without_run_config_uses_cache(self) -> None:
        """Config factory falls back to cached base when run_config is not provided."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_base = Mock()
        mock_base.copy = Mock(return_value=mock_base)
        service._base_graph_cache["test_graph"] = mock_base

        factory_called = False

        async def make_graph(config: dict) -> Mock:
            nonlocal factory_called
            factory_called = True
            return Mock()

        service._graph_factories["test_graph"] = GraphFactory(
            factory=make_graph,
            kind="config",
        )

        with patch("aegra_api.core.database.db_manager") as mock_db_manager:
            mock_db_manager.get_checkpointer = Mock(return_value="cp")
            mock_db_manager.get_store = Mock(return_value="st")

            async with service.get_graph("test_graph") as graph:
                assert graph == mock_base

        assert not factory_called

    @pytest.mark.asyncio
    async def test_get_base_graph_config_factory_calls_with_empty_dict(self) -> None:
        """_get_base_graph calls config factory with {} to get default graph."""
        service = LangGraphService()
        service._graph_registry = {"test_graph": {"file_path": "test.py", "export_name": "graph"}}

        mock_compiled = Mock()
        call_log: list[dict] = []

        async def make_graph(config: dict) -> Mock:
            call_log.append(config)
            return mock_compiled

        factory = GraphFactory(factory=make_graph, kind="config")

        with patch.object(service, "_load_graph_from_file", return_value=factory):
            result = await service._get_base_graph("test_graph")

        assert result is mock_compiled
        assert len(call_log) == 1
        assert call_log[0] == {}
        assert service._graph_factories["test_graph"] is factory

    @pytest.mark.asyncio
    async def test_runtime_param_takes_precedence_over_config(self) -> None:
        """A factory with both `runtime` and `config` params is detected as runtime factory."""
        service = LangGraphService()

        mock_graph = Mock()

        async def make_graph(runtime: Runtime, config: dict) -> Mock:
            return mock_graph

        mock_module = Mock()
        mock_module.graph = make_graph

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module_from_spec,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()
            mock_module_from_spec.return_value = mock_module

            graph_info = {"file_path": "test.py", "export_name": "graph"}
            result = await service._load_graph_from_file("test_graph", graph_info)

            assert isinstance(result, GraphFactory)
            assert result.kind == "runtime"
