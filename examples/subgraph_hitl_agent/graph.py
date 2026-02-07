"""Minimal subgraph example used for testing subgraph state inspection."""

from typing import TypedDict

from langgraph.graph import START, StateGraph
from langgraph.types import interrupt


class State(TypedDict):
    foo: str


def subgraph_set_state(state: State) -> State:  # noqa: ARG001
    return {"foo": "Initial subgraph value."}


def subgraph_node(state: State) -> State:
    """Interrupt to request a value before resuming the subgraph."""
    value = interrupt("Provide value:")
    return {"foo": state["foo"] + value}


subgraph_builder = StateGraph(State)
subgraph_builder.add_node(subgraph_set_state)
subgraph_builder.add_node(subgraph_node)
subgraph_builder.add_edge(START, "subgraph_set_state")
subgraph_builder.add_edge("subgraph_set_state", "subgraph_node")
subgraph_builder.add_edge("subgraph_node", "__end__")
subgraph = subgraph_builder.compile()


builder = StateGraph(State)
builder.add_node("node_1", subgraph)
builder.add_edge(START, "node_1")
builder.add_edge("node_1", "__end__")

graph = builder.compile()
