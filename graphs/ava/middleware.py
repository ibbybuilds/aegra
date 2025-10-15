from langchain.agents.middleware import AgentMiddleware
from ava.state import HotelSearchState

class HotelSearchMiddleware(AgentMiddleware):
    name = "hotel_search_middleware"
    state_schema = HotelSearchState