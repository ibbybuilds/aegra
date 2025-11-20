"""AVA agent graph - loads from ava-core package.

This file acts as a bridge to the ava-core package, making AVA work
exactly like other graphs in the system (loaded via langgraph_service.get_graph).
"""

from ava_core.public import build_hotel_agent

# Create the agent using the factory method
# This will be cached by langgraph_service.get_graph() just like other graphs
agent = build_hotel_agent(config={"recursion_limit": 1000})
