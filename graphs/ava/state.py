from langchain.agents.middleware import AgentState
from typing import NotRequired


class HotelSearchState(AgentState):
    # Search parameters (stored in hotelParams for consistency)
    location: NotRequired[str]  # User-friendly location name for display
    
    # VFS state tracking (optimized for voice/speed)
    hotelSearchKey: NotRequired[str]  # Current hotel search identifier
    roomSearchKey: NotRequired[str]   # Current room search identifier
    hotelToken: NotRequired[str]      # API token from hotel_search (for rooms_and_rates)
    hotelCursor: NotRequired[str]     # Current position in hotel VFS array
    roomCursor: NotRequired[str]      # Current position in room VFS array
    hotelParams: NotRequired[dict]    # Last hotel search params (dates, occupancy, filters, circularRegion)
    roomParams: NotRequired[dict]     # Last room search params
    hotelMeta: NotRequired[dict]      # Metadata (fetchedAt, ttlSec, status)
    roomMeta: NotRequired[dict]       # Metadata (fetchedAt, ttlSec, status)