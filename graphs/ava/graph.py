import os
from deepagents import create_deep_agent
from ava.middleware import HotelSearchMiddleware
from ava.state import HotelSearchState
from ava.prompts import *
from ava.tools.internet_search import internet_search
from ava.tools.detail import hotel_details, policy_qa
from ava.tools import get_next_hotels, get_next_rooms
from ava.tools.explore import * 


explore_sub_agent = {
    "name": "explore-sub-agent",
    "description": "Explore and search for hotels and rooms that match the user's criteria, including location, dates, and any specific filters or preferences they provide.",
    "prompt": sub_explore_prompt,
    "tools": [query_hotel_name, get_geo_coordinates, hotel_search, rooms_and_rates],
    "model_settings": {
        "model_name": "anthropic:claude-3-5-haiku-20241022",
        "temperature": 0,
    },
    "middleware": [HotelSearchMiddleware()]
}

detail_sub_agent = {
    "name": "detail-sub-agent",
    "description": "Provides structured hotel and room comparisons, answers company policy or amenity questions, summarizes room details, explains features or policies, and highlights key differences for user decisions.",
    "prompt": sub_detail_prompt,
    "tools": [hotel_details, policy_qa, internet_search, rooms_and_rates],
    "model_settings": {
        "model_name": "anthropic:claude-3-5-haiku-20241022",
        "temperature": 0,
    },
}

research_sub_agent = {
    "name": "research-sub-agent",
    "description": "Used to research general questions not covered by hotel/room data. Only give this researcher one topic at a time. Do not pass multiple sub questions to this researcher. Instead, you should break down a large topic into the necessary components, and then call multiple research agents in parallel, one for each sub question. Use for restaurant information, local attractions, distances, and area details that complement hotel search results.",
    "prompt": sub_research_prompt,
    "tools": [internet_search],
    "model_settings": {
        "model_name": "anthropic:claude-3-5-haiku-20241022",
        "temperature": 0,
    },
}

# Create the hotel agent with pagination tools available to main agent
agent = create_deep_agent(
    instructions=agent_instructions,
    tools=[get_next_hotels, get_next_rooms],
    subagents=[explore_sub_agent, research_sub_agent, detail_sub_agent],
    middleware=[HotelSearchMiddleware()],
    context_schema=HotelSearchState,  # Use our custom state schema
).with_config(recursion_limit=1000)
