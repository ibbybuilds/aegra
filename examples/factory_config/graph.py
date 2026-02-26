"""Config factory example — model selection via RunnableConfig.

The factory receives the request's RunnableConfig dict on every invocation,
allowing callers to override the model at runtime through
``config["configurable"]["model"]``.

Usage in aegra.json::

    {
      "graphs": {
        "config_factory": "./examples/factory_config/graph.py:graph"
      }
    }
"""

from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

from factory_config.utils import load_chat_model

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "openai/gpt-4o-mini"


class State(TypedDict):
    """Minimal chat state."""

    messages: list[AnyMessage]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def call_model(state: State, config: RunnableConfig) -> dict[str, list[AIMessage]]:
    """Call the LLM with the model specified in config."""
    model_name = config.get("configurable", {}).get("model", DEFAULT_MODEL)
    model = load_chat_model(model_name)

    response = cast(
        "AIMessage",
        await model.ainvoke(state["messages"]),
    )
    return {"messages": [response]}


def route_output(state: State) -> Literal["__end__", "call_model"]:
    """End if the model didn't request tool calls."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and not last.tool_calls:
        return "__end__"
    return "call_model"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def graph(config: dict[str, Any]) -> CompiledStateGraph:
    """Config factory — called per-request with the RunnableConfig.

    The ``model`` key in ``config["configurable"]`` selects the LLM.
    Falls back to ``DEFAULT_MODEL`` when not specified.
    """
    builder = StateGraph(State)
    builder.add_node("call_model", call_model)
    builder.add_edge("__start__", "call_model")
    builder.add_conditional_edges("call_model", route_output)
    return builder.compile(name="Config Factory Agent")
