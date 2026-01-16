"""Graph configuration for ava_v1 agent."""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware, SummarizationMiddleware
from langchain.chat_models import init_chat_model
from langgraph.graph.state import CompiledStateGraph

from ava_v1.middleware import ForcedRetryMiddleware, customize_agent_prompt
from ava_v1.prompt import TRAVEL_ASSISTANT_PROMPT
from ava_v1.state import AvaV1State
from ava_v1.tools import (
    book_room,
    hotel_details,
    internet_search,
    modify_call,
    query_vfs,
    start_hotel_search,
    start_room_search,
    update_customer_details,
)

model = init_chat_model(
    "anthropic:claude-haiku-4-5-20251001", temperature=0.3, timeout=30, max_retries=3
)

summarization_model = init_chat_model("google_genai:gemini-2.5-flash-lite")

agent: CompiledStateGraph = create_agent(
    model=model,
    tools=[
        start_hotel_search,
        start_room_search,
        query_vfs,
        hotel_details,
        book_room,
        modify_call,
        internet_search,
        update_customer_details,
    ],
    system_prompt=TRAVEL_ASSISTANT_PROMPT,  # Base prompt (will be replaced by dynamic prompt)
    middleware=[
        SummarizationMiddleware(
            model=summarization_model,
            max_tokens_before_summary=20000,
            messages_to_keep=15,
        ),
        ModelFallbackMiddleware(
            "anthropic:claude-haiku-3-5",
            "google_genai:gemini-2.5-flash-lite",
            "gpt-4o-mini",
        ),
        customize_agent_prompt,
        ForcedRetryMiddleware(),
    ],  # Dynamic prompt based on CallContext
    state_schema=AvaV1State,
)

__all__ = ["agent"]
