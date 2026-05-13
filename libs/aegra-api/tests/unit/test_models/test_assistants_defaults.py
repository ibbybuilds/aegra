"""Regression: AssistantCreate / AssistantUpdate must not share mutable default dicts.

Pydantic v2 currently deep-copies on assignment so the historical
`Field({})` shape hasn't bitten us, but the pattern is brittle. These tests
pin the safe `default_factory=dict` behavior so a future revert can't sneak
shared state across instances.
"""

from aegra_api.models.assistants import AssistantCreate, AssistantUpdate


def test_assistant_create_defaults_do_not_share_state() -> None:
    a = AssistantCreate(graph_id="agent")
    b = AssistantCreate(graph_id="agent")
    assert a.config is not None
    assert a.context is not None
    assert a.metadata is not None

    a.config["x"] = 1
    a.context["y"] = 2
    a.metadata["z"] = 3

    assert b.config == {}
    assert b.context == {}
    assert b.metadata == {}


def test_assistant_update_defaults_do_not_share_state() -> None:
    a = AssistantUpdate()
    b = AssistantUpdate()
    assert a.config is not None
    assert a.context is not None
    assert a.metadata is not None

    a.config["x"] = 1
    a.context["y"] = 2
    a.metadata["z"] = 3

    assert b.config == {}
    assert b.context == {}
    assert b.metadata == {}


def test_assistant_create_defaults_are_distinct_instances() -> None:
    a = AssistantCreate(graph_id="agent")
    b = AssistantCreate(graph_id="agent")

    assert a.config is not b.config
    assert a.context is not b.context
    assert a.metadata is not b.metadata


def test_assistant_update_defaults_are_distinct_instances() -> None:
    a = AssistantUpdate()
    b = AssistantUpdate()

    assert a.config is not b.config
    assert a.context is not b.context
    assert a.metadata is not b.metadata
