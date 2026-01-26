# AVA Prompt Architecture & Context-Aware Workflows

## Overview

This document explains the architectural principles behind ava_v1's dynamic prompt system and context-aware workflow optimization. The system enables different conversation entry points to follow different execution paths, reducing unnecessary API calls and improving the user experience.

## Core Principles

### 1. Separation of Concerns

**Static Base Logic** (`HOME_PAGE_PROMPT` in `prompt.py`):
- Unchanging general instructions
- Core tool descriptions
- Universal workflow patterns
- Always included regardless of context

**Dynamic Contextual Instructions** (`base_prompt.j2` template):
- Context-specific instructions
- Entry point-specific workflows
- Priority-based prompt injection
- Dynamically rendered at runtime based on call context

**Benefits**:
- Maintainability: Changes to general logic don't affect context-specific instructions
- Clarity: Each entry point has explicit, isolated instructions
- Flexibility: Easy to add new entry points or modify existing ones

### 2. Context-Aware Workflow Optimization

Different entry points require different workflows to avoid unnecessary operations:

```
General Entry → Full workflow (search hotels → present → search rooms)
Property Entry → Skip hotel search (user already on specific hotel page)
Dated Property → Skip hotel search + partial params (dates already provided)
```

This reduces:
- API calls to hotel search service
- Token usage in prompts
- User friction (fewer questions to ask)
- Response latency

## 5-Level Priority System

The priority system determines which contextual instructions to inject into the prompt.

### Priority 1: Abandoned Payment
**Trigger**: `context.abandoned_payment` exists
**Type Values**: `abandoned_payment` or `abandoned_payment_with_thread`
**Use Case**: Customer started booking but didn't complete payment

**Workflow**:
- Acknowledge the abandoned payment immediately
- Proactively offer to complete the booking
- Reference the amount and details
- Create urgency based on time since abandonment
- Streamline the completion process

**Example Entry**: Customer clicks payment recovery link after 10 minutes

---

### Priority 2: Dated Property
**Trigger**: `context.property` AND `context.booking` exist
**Type Value**: `dated_property`
**Use Case**: Customer lands on hotel page with dates already in URL/context

**Workflow**:
1. Acknowledge property and dates: "I see you're interested in [Hotel] for [dates]"
2. Collect occupancy (adults, children, rooms)
3. Call `start_room_search(hotel_id)` directly (NO hotel_search needed)
4. Present room options

**Example Entry**: User clicks "Book Now" on hotel page with date picker already filled

**Optimization**: Skips hotel search entirely + partially pre-filled parameters

---

### Priority 3: Property-Specific (GA Call Extension)
**Trigger**: `context.type == "property_specific"` AND `context.property` exists
**Type Value**: `ga_call_extension`
**Use Case**: Customer lands on specific hotel page (Google Ad click, direct link)

**Workflow**:
1. Acknowledge the property: "I can help you book at [Hotel]"
2. Collect dates using `update_search_params` (checkIn, checkOut)
3. Collect occupancy using `update_search_params` (numOfAdults, childAges, numOfRooms)
4. Call `start_room_search(hotel_id)` directly (NO hotel_search needed)
5. Present room options

**Example Entry**: User clicks Google Ad for "JW Marriott Miami"

**Optimization**: Skips hotel search entirely

---

### Priority 4: Payment Return
**Trigger**: `context.type == "payment_return"` AND `context.payment` exists
**Type Value**: `payment_return`
**Use Case**: Customer returns after payment attempt (success, failure, or pending)

**Workflow**:
- Acknowledge payment status immediately
- Provide appropriate next steps based on status
- Offer assistance with any issues
- Confirm booking details if successful

**Example Entry**: Customer redirected back after Stripe payment

---

### Priority 5: General (Default)
**Trigger**: No other context matches
**Type Value**: `general`
**Use Case**: Customer starts fresh conversation from homepage

**Workflow**:
1. Greet and ask about travel needs
2. Collect destination
3. Collect dates using `update_search_params`
4. Collect occupancy using `update_search_params`
5. Confirm all parameters with user
6. Call `start_hotel_search(searches=[...])` with full parameters
7. Present hotel options (top 3)
8. User selects hotel → call `start_room_search`
9. Present room options

**Example Entry**: User visits homepage and starts typing "I need a hotel"

**Full Workflow**: All steps required, no optimizations

## Context Derivation Flow

The system automatically derives context from the runtime state when explicit context isn't provided:

```python
# Priority order for derivation:
1. Explicit call_context (payment_return, abandoned_payment, session)
   └─ Provided via /state endpoint or external system

2. Auto-derive from active_searches state
   ├─ hotel_id + booking_info → "dated_property"
   ├─ hotel_id only → "property_specific"
   └─ booking_info only → "general"

3. Message history check
   └─ len(messages) > 2 → "general" (continuing conversation)

4. Default
   └─ "general"
```

**Implementation**: `middleware.py::extract_call_context()`

## Tool Architecture

All 9 ava_v1 tools have Pydantic schemas for type validation and LLM guidance.

### State Management Tools

**`update_search_params`** - Staging area for search parameters
- Collects dates/occupancy incrementally (one field at a time)
- Validates each field before storing
- Used by property-specific flows to avoid hotel_search
- Parameters staged here are automatically consumed by `start_room_search`

**`update_customer_details`** - Customer information collection
- Collects first_name, last_name, email sequentially
- Each field saved immediately after spelling confirmation
- Persistent across conversation (stored in state)

### Search Tools

**`start_hotel_search`** - Initiate hotel search (async)
- Used in general workflow when hotel is unknown
- Returns search status (cached/polling)
- Creates `search_key` for later queries
- Can resolve hotel names to IDs (e.g., "JW Marriott" → hotel_id)

**`start_room_search`** - Initiate room search (async)
- Used in ALL workflows once hotel is known
- Two modes:
  - **With search_key**: After hotel_search (general workflow)
  - **Without search_key**: Property-specific workflows (uses update_search_params data)
- Returns room search status

**`query_vfs`** - Query/filter cached search results
- Retrieves complete results after search completes
- Supports JSONPath filtering, sorting, pagination
- CRITICAL: Only source of complete room data with token/rate_key for booking

### Booking Tools

**`book_room`** - Create 10-minute hold and prepare payment
- Requires complete room data from query_vfs (not firstRoom preview)
- Validates customer info exists
- Creates booking hold
- Returns payment URL (SMS or phone)

**`hotel_details`** - Get property information
- Descriptions, amenities, policies
- Supports both ID and name lookup
- Used when user asks about facilities

### Utility Tools

**`internet_search`** - Tavily web search
- Weather, events, hotel reviews
- Helps with recommendation context

**`modify_call`** - End call or transfer
- Signals: end_call, transfer_to_payment, transfer_to_agent
- Includes handoff context for live agents

## Workflow Comparison

### General Workflow (Priority 5)
```
Entry: Homepage, no context
Steps: 8-10 tool calls
API Calls: Hotel search + Room search

1. User: "I need a hotel in Miami"
2. Agent: Asks for dates
3. User: "February 1-3"
4. Agent: update_search_params("checkIn", "2026-02-01")
5. Agent: update_search_params("checkOut", "2026-02-03")
6. Agent: Asks for occupancy
7. User: "2 adults"
8. Agent: update_search_params("numOfAdults", 2)
9. Agent: Confirms all parameters
10. User: "Yes"
11. Agent: start_hotel_search([{destination: "Miami", ...}])
12. Agent: query_vfs("Miami") → present 3 hotels
13. User: "I like the JW Marriott"
14. Agent: start_room_search(hotel_id="123", search_key="Miami")
15. Agent: query_vfs("Miami:rooms:123") → present rooms
```

### Property-Specific Workflow (Priority 3)
```
Entry: Hotel page (Google Ad, direct link)
Steps: 4-6 tool calls
API Calls: Room search only (NO hotel search)

1. User lands on JW Marriott Miami page
   Context: {type: "property_specific", property: {hotel_id: "123"}}
2. Agent: "I can help you book at JW Marriott Miami. What dates?"
3. User: "February 1-3"
4. Agent: update_search_params("checkIn", "2026-02-01")
5. Agent: update_search_params("checkOut", "2026-02-03")
6. Agent: "How many adults?"
7. User: "2 adults"
8. Agent: update_search_params("numOfAdults", 2)
9. Agent: Confirms details
10. User: "Yes"
11. Agent: start_room_search(hotel_id="123") ← NO search_key needed!
12. Agent: query_vfs("{hotel_name}:rooms:123") → present rooms
```

**Savings**:
- ✓ Skipped hotel search API call
- ✓ Reduced from 15 → 12 steps
- ✓ Fewer questions (destination already known)
- ✓ Faster to booking

### Dated Property Workflow (Priority 2)
```
Entry: Hotel page with dates pre-filled
Steps: 3-4 tool calls
API Calls: Room search only

1. User lands on JW Marriott Miami page with dates in URL
   Context: {
     type: "dated_property",
     property: {hotel_id: "123"},
     booking: {checkIn: "2026-02-01", checkOut: "2026-02-03"}
   }
2. Agent: "I see you're interested in JW Marriott for Feb 1-3. How many guests?"
3. User: "2 adults"
4. Agent: update_search_params("numOfAdults", 2)
5. Agent: Confirms details
6. User: "Yes"
7. Agent: start_room_search(hotel_id="123")
8. Agent: query_vfs("{hotel_name}:rooms:123") → present rooms
```

**Savings**:
- ✓ Skipped hotel search API call
- ✓ Reduced from 15 → 8 steps
- ✓ Even fewer questions (dates + hotel known)
- ✓ Fastest path to booking

## Technical Implementation

### Template Rendering (template.py)

**Singleton Pattern**:
- Template compiled once on first access
- Cached forever (significant performance gain)
- No recompilation overhead on every request

**Date Context Caching**:
- LRU cache with maxsize=1
- Automatically clears when date changes
- 99%+ reduction in date calculations

**Priority Determination**:
```python
def _determine_priority(context: CallContext) -> str:
    # Early returns for performance
    if context.abandoned_payment:
        return "abandoned_payment_with_thread" if context.type == "thread_continuation" else "abandoned_payment"

    if context.property and context.booking:
        return "dated_property"

    if context.type == "property_specific" and context.property:
        return "ga_call_extension"

    if context.type == "payment_return" and context.payment:
        return "payment_return"

    return "general"
```

### Middleware Integration (middleware.py)

**Dynamic Prompt Replacement**:
- `@dynamic_prompt` decorator replaces entire system prompt
- Accesses context via `request.runtime.context` (preferred) or `request.state` (fallback)
- Returns fully customized prompt string

**Context Extraction**:
- Explicit context from runtime.context (highest priority)
- Auto-derivation from state.active_searches (smart fallback)
- Message history check (thread continuations)
- Default to general (safest fallback)

### State Management (state.py)

**Custom Reducers**:
- `merge_dicts`: Parallel tool updates to same dict field
- `context_stack_reducer`: Both append and replace operations
- Enables proper state merging with LangGraph

**State Fields**:
- `active_searches`: Label-based search tracking (e.g., "Miami", "Miami:JW Marriott")
- `search_params`: Staging area for incremental parameter collection
- `context_stack`: Conversational focus tracking
- `customer_details`: Verified customer information
- `call_context`: Dynamic context from /state endpoint

## Benefits & Trade-offs

### Benefits

**Performance**:
- Reduced API calls (skip hotel_search when hotel known)
- Lower token usage (smaller, focused prompts)
- Faster response times (fewer steps)

**User Experience**:
- Fewer questions (parameters from context)
- Faster to booking (optimized workflows)
- More natural conversations (context-aware)

**Maintainability**:
- Clear separation of concerns
- Isolated entry point logic
- Easy to add new entry points
- Self-documenting workflows

**Reliability**:
- Type validation via Pydantic schemas
- Early error detection
- Better LLM tool understanding

### Trade-offs

**Complexity**:
- More sophisticated context derivation logic
- Multiple workflow paths to maintain
- Requires understanding of priority system

**Testing**:
- Must test each entry point independently
- More integration test scenarios
- Context derivation edge cases

**Debugging**:
- Need to trace which priority triggered
- Multiple code paths for same outcome
- Requires good logging (already implemented)

## Future Considerations

### Potential Extensions

**New Entry Points**:
- Loyalty program member context (pre-filled customer details)
- Corporate booking context (billing info, approval flows)
- Group booking context (multiple rooms with constraints)
- Rewards redemption context (points + cash workflows)

**Enhanced Optimizations**:
- Partial date context (e.g., month known but not specific dates)
- Occupancy preferences from profile (frequent business traveler = 1 adult, 1 room)
- Budget context from previous bookings (user typically books $100-150/night)

**A/B Testing Framework**:
- Different prompt strategies per entry point
- Measure conversion rates by workflow
- Optimize based on completion metrics

### Monitoring & Analytics

**Key Metrics to Track**:
- Entry point distribution (which priorities are most common)
- Workflow completion rates by entry point
- Average steps to booking by priority
- API call reduction impact
- Token usage by priority level

**Logging Enhancements**:
- Priority assignment reasoning
- Context derivation decisions
- Workflow path taken
- Tool call sequences

## Summary

The ava_v1 prompt architecture achieves context-aware workflow optimization through:

1. **Priority-based prompt customization** - Different instructions for different entry points
2. **Smart context derivation** - Automatic detection of user's starting point
3. **Workflow shortcuts** - Skip unnecessary steps when context provides answers
4. **Type-safe tool schemas** - Validation and LLM guidance
5. **Clean separation of concerns** - Maintainable, extensible architecture

This foundation enables ava_v1 to provide fast, efficient booking experiences while maintaining flexibility for future enhancements.

---

**Last Updated**: January 22, 2026
**Related Files**:
- `graphs/ava_v1/prompts/template.py` - Priority determination and template rendering
- `graphs/ava_v1/prompts/base_prompt.j2` - Context-specific instructions
- `graphs/ava_v1/middleware.py` - Context derivation and prompt injection
- `graphs/ava_v1/state.py` - State management and reducers
- `graphs/ava_v1/tools/` - All tool implementations with Pydantic schemas
