# ava_v1 - ADK to LangChain Conversion

Hotel search and booking agent with ADK-style state management, converted to LangChain/LangGraph.

## Overview

This package contains a complete conversion of ADK (Anthropic Development Kit) tools to LangChain format, preserving the original state management patterns while adapting to LangChain's Command pattern for state updates.

## Architecture

### State Management

The agent uses a simplified state schema with two main fields:

- **active_searches**: Label-based search tracking (e.g., "Miami", "Miami:JW Marriott")
  - Format: `{"Miami": {"searchId": "abc", "status": "cached", ...}}`

- **context_stack**: Conversational focus tracking stack
  - Format: `[{"type": "HotelList", "search_key": "Miami"}, ...]`
  - Types: HotelList, RoomList, HotelDetails, RoomSelected, BookingPending

### Custom Reducers

Two custom reducers enable proper state updates:

1. **merge_dicts**: Merges dict fields with right precedence (for active_searches)
2. **context_stack_reducer**: Handles both append and replace operations
   - Append: `[context_object]` - pushes new context
   - Replace: `{"__replace__": new_stack}` - for pop operations

## Tools

### Explore Tools
- **get_geo_coordinates**: Google Places API geocoding with Redis cache
- **hotel_search**: Hotel search with polling, supports name resolution
- **rooms_and_rates**: Room inventory lookup with state updates
- **query_vfs**: Complex Redis JSON queries with JSONPath filtering

### Detail Tools
- **hotel_details**: Hotel details with Redis caching

### Book Tools
- **book_room**: Complex booking with price verification, validation, and context_stack updates

### Call Management
- **modify_call**: Call end/payment transfer signals

### State Management
- **push_context**: Push to context_stack with validation rules
- **pop_context**: Pop from context_stack using replacement pattern

## Usage

### Basic Usage

```python
from langchain_anthropic import ChatAnthropic
from ava_v1 import create_ava_v1_agent

# Initialize the language model
model = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0,
)

# Create the agent
agent = create_ava_v1_agent(model=model)

# Use the agent
result = agent.invoke({
    "messages": [
        {"role": "user", "content": "Find me hotels in Miami for Dec 26-29"}
    ]
})

print(result["messages"][-1].content)
```

### Custom System Prompt

```python
agent = create_ava_v1_agent(
    model=model,
    system_prompt="You are a hotel booking expert..."
)
```

### Accessing State

```python
result = agent.invoke({"messages": [...]})

# Check active searches
if "active_searches" in result:
    print("Active searches:", result["active_searches"])

# Check context stack
if "context_stack" in result:
    print("Context stack:", result["context_stack"])
```

## Conversion Details

### Key Conversion Patterns

1. **State Access**: `tool_context.state.get()` → `runtime.state.get()`
2. **State Updates**: Direct mutation → `Command(update={...})`
3. **Tool Decorator**: None → `@tool(description="...")`
4. **Runtime Injection**: `tool_context: ToolContext` → `runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None`
5. **Returns**: Dict → `Command | str` (Command for state updates, str for read-only)

### Example Tool Conversion

**Before (ADK)**:
```python
async def hotel_search(tool_context: ToolContext, searches: List[Dict]) -> Dict:
    # Process searches...

    # Update state
    tool_context.state["active_searches"] = active_searches

    return {"searches": searches_metadata}
```

**After (LangChain)**:
```python
@tool(description="Initiate hotel searches")
async def hotel_search(
    searches: List[Dict[str, Any]],
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    # Process searches...

    # Return Command with state updates
    return Command(
        update={
            "messages": [ToolMessage(...)],
            "active_searches": active_searches,  # Will be merged
        }
    )
```

## Dependencies

- langgraph
- langchain
- langchain-anthropic
- httpx
- redis
- Other dependencies as specified in pyproject.toml

## File Structure

```
ava_v1/
├── __init__.py           # Package exports
├── state.py              # State schema with custom reducers
├── middleware.py         # Middleware configuration
├── graph.py              # Agent creation and configuration
├── shared_libraries/     # Utility functions (copied from ADK)
│   ├── hashing.py
│   ├── validation.py
│   ├── lookup_id.py
│   ├── redis_helpers.py
│   └── input_sanitizer.py
└── tools/               # Converted tools
    ├── explore/         # Hotel and room search tools
    ├── detail/          # Hotel details tools
    ├── book/            # Booking tools
    ├── call/            # Call management tools
    └── state/           # State management tools
```

## Notes

- All tools preserve the original ADK business logic
- Redis integration is maintained for caching and polling
- Validation and error handling are preserved from ADK
- The agent uses LangGraph's `create_react_agent` for the ReAct pattern
- All async operations are supported by LangChain

## License

Same as parent project.
