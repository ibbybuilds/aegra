import json
import time
from typing import Annotated, Union, Dict, List, Any
from langchain.tools import tool, InjectedToolCallId, InjectedState
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from ava.utils.ranking.cursors import read_cursor, make_cursor
from ava.utils.ranking.policies import VERSION
import msgspec


@tool(description="Get next hotel slice from cached results using state-based pagination.")
async def get_next_hotels(
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    hotelSearchKey: Annotated[str, InjectedState("hotelSearchKey")] = None,
    hotelCursor: Annotated[str, InjectedState("hotelCursor")] = "",
    hotelMeta: Annotated[dict, InjectedState("hotelMeta")] = None,
    files_dict: Annotated[dict, InjectedState("files")] = None,
    limit: int = 3
) -> Union[Command, str]:
    """
    Get next slice of hotels from VFS cache using state-based pagination.
    
    Args:
        limit: Number of hotels to return (defaults to 3)
        tool_call_id: Tool call ID for tracking (injected automatically)
        state: Agent state containing VFS files_dict and pagination info (injected automatically)
    
    Returns:
        Command with next slice of hotels and updated cursor
    """
    try:
        # Validate injected parameters
        if not tool_call_id:
            tool_call_id = "pagination_error"
        
        if not hotelSearchKey:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "No hotel search found. Please run a hotel search first.",
                                "hotels": [],
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Get pagination info from injected parameters
        search_key = hotelSearchKey
        current_cursor = hotelCursor
        hotel_meta = hotelMeta or {}
        
        # Check TTL expiration
        fetched_at = hotel_meta.get("fetchedAt", 0)
        ttl_sec = hotel_meta.get("ttlSec", 600)
        current_time = int(time.time())
        
        if current_time > (fetched_at + ttl_sec):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "Cached results expired. Please re-run hotel search.",
                                "hotels": [],
                                "nextCursor": None,
                                "expired": True
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Read VFS file: hotels_{searchKey}.json
        vfs_filename = f"hotels_{search_key}.json"
        files_dict_dict = files_dict or {}
        
        if vfs_filename not in files_dict:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": f"No cached hotel results found for search key: {search_key}",
                                "hotels": [],
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Parse cached results using msgspec for better performance
        try:
            cached_data = msgspec.json.decode(files_dict[vfs_filename])
        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": f"Failed to parse cached results: {str(e)}",
                                "hotels": [],
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Extract vfsHotels array from cached results
        vfs_hotels = cached_data.get("vfsHotels", [])
        
        if not vfs_hotels:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "No hotels found in cached results",
                                "hotels": [],
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Decode current cursor to get position
        try:
            if current_cursor:
                cursor_data = read_cursor(current_cursor)
                pos = cursor_data.get("pos", 0)
            else:
                pos = 0
        except Exception as e:
            pos = 0  # Start from beginning if cursor is invalid
        
        # Check if VFS exhausted
        if pos >= len(vfs_hotels):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "hotels": [],
                                "nextCursor": None,
                                "exhausted": True,
                                "message": "No more hotels available"
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Slice from pos to pos+limit
        end_pos = min(pos + limit, len(vfs_hotels))
        hotels_slice = vfs_hotels[pos:end_pos]
        
        # Create new cursor at pos+limit
        new_cursor = make_cursor(search_key, end_pos, VERSION)
        
        # Format response
        response = {
            "hotels": hotels_slice,
            "nextCursor": new_cursor if end_pos < len(vfs_hotels) else None,
            "totalAvailable": len(vfs_hotels),
            "returned": len(hotels_slice),
            "position": f"{pos}-{end_pos-1}"
        }
        
        # Update state with new cursor
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=msgspec.json.encode(response).decode('utf-8'),
                        tool_call_id=tool_call_id
                    )
                ],
                # Update the cursor in state for next pagination
                "hotelCursor": new_cursor if end_pos < len(vfs_hotels) else None
            }
        )
        
    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "error": f"Unexpected error: {str(e)}",
                            "hotels": [],
                            "nextCursor": None
                        }, indent=2),
                        tool_call_id=tool_call_id or "pagination_error"
                    )
                ]
            }
        )


@tool(description="Get next room option from cached results using state-based pagination.")
async def get_next_rooms(
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    roomSearchKey: Annotated[str, InjectedState("roomSearchKey")] = None,
    roomCursor: Annotated[str, InjectedState("roomCursor")] = "",
    roomMeta: Annotated[dict, InjectedState("roomMeta")] = None,
    files_dict: Annotated[dict, InjectedState("files")] = None,
    limit: int = 1,
) -> Union[Command, str]:
    """
    Get next room option from VFS cache using state-based pagination.
    
    Args:
        limit: Number of rooms to return (defaults to 1)
        tool_call_id: Tool call ID for tracking (injected automatically)
        state: Agent state containing VFS files_dict and pagination info (injected automatically)
    
    Returns:
        Command with next room option and updated cursor
    """
    try:
        # Validate injected parameters
        if not tool_call_id:
            tool_call_id = "pagination_error"
        
        if not roomSearchKey:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "No room search found in state. Please run a room search first.",
                                "room": None,
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Get pagination info from injected parameters
        search_key = roomSearchKey
        current_cursor = roomCursor
        room_meta = roomMeta or {}
        
        # Check TTL expiration
        fetched_at = room_meta.get("fetchedAt", 0)
        ttl_sec = room_meta.get("ttlSec", 600)
        current_time = int(time.time())
        
        if current_time > (fetched_at + ttl_sec):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "Cached results expired. Please re-run room search.",
                                "room": None,
                                "nextCursor": None,
                                "expired": True
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Read VFS file: rooms_{searchKey}.json
        vfs_filename = f"rooms_{search_key}.json"
        files_dict_dict = files_dict or {}
        
        if vfs_filename not in files_dict_dict:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": f"No cached room results found for search key: {search_key}",
                                "room": None,
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Parse cached results using msgspec for better performance
        try:
            cached_data = msgspec.json.decode(files_dict_dict[vfs_filename])
        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": f"Failed to parse cached results: {str(e)}",
                                "room": None,
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Extract vfsRooms array from cached results
        vfs_rooms = cached_data.get("vfsRooms", [])
        
        if not vfs_rooms:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": "No rooms found in cached results",
                                "room": None,
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Decode current cursor to get position
        try:
            if current_cursor:
                cursor_data = read_cursor(current_cursor)
                pos = cursor_data.get("pos", 0)
            else:
                pos = 0
        except Exception as e:
            pos = 0  # Start from beginning if cursor is invalid
        
        # Check if VFS exhausted
        if pos >= len(vfs_rooms):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "room": None,
                                "nextCursor": None,
                                "exhausted": True,
                                "message": "No more rooms available"
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        # Slice from pos to pos+limit
        end_pos = min(pos + limit, len(vfs_rooms))
        rooms_slice = vfs_rooms[pos:end_pos]
        
        # Create new cursor at pos+limit
        new_cursor = make_cursor(search_key, end_pos, VERSION)
        
        # Format response (rooms typically return single room)
        response = {
            "room": rooms_slice[0] if rooms_slice else None,
            "nextCursor": new_cursor if end_pos < len(vfs_rooms) else None,
            "totalAvailable": len(vfs_rooms),
            "returned": len(rooms_slice),
            "position": f"{pos}-{end_pos-1}"
        }
        
        # Update state with new cursor
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=msgspec.json.encode(response).decode('utf-8'),
                        tool_call_id=tool_call_id
                    )
                ],
                # Update the cursor in state for next pagination
                "roomCursor": new_cursor if end_pos < len(vfs_rooms) else None
            }
        )
        
    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "error": f"Unexpected error: {str(e)}",
                            "room": None,
                            "nextCursor": None
                        }, indent=2),
                        tool_call_id=tool_call_id or "pagination_error"
                    )
                ]
            }
        )