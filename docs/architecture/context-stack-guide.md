# Context Stack Guide for Background Workers

This document explains how to build `context_stack` and `active_searches` state objects from user website browsing activity. These objects are passed to initialize the agent state when a user calls.

## Overview

The `context_stack` is a **focus tracking stack** that maintains conversational context based on what the user is currently viewing. It works like browser history - as users drill down (hotels → rooms → details), contexts are pushed onto the stack. The top of the stack represents the current focus.

## Context Types

### 1. HotelList
**When**: User is viewing a list of hotels for a destination
**Structure**:
```json
{
  "type": "HotelList",
  "search_key": "Miami"  // Label from active_searches
}
```

### 2. RoomList
**When**: User is viewing available rooms for a specific hotel
**Structure**:
```json
{
  "type": "RoomList",
  "search_key": "Miami",  // Original search label
  "hotel_id": "123abc",
  "roomSearchId": "rooms_hash_xyz"  // Hash of hotel_id + dates + occupancy
}
```

### 3. HotelDetails
**When**: User is viewing detailed information about a hotel (amenities, photos, reviews)
**Structure**:
```json
{
  "type": "HotelDetails",
  "hotel_id": "123abc"
}
```

### 4. BookingPending
**When**: User has initiated a booking and is in payment flow
**Structure**:
```json
{
  "type": "BookingPending",
  "booking_hash": "booking_xyz",
  "session_id": "session_123",
  "payment_type": "phone",
  "hold_expires_at": "2025-01-14T12:00:00Z",
  "amount": 299.99,
  "s3_key": "bookings/xyz.json"
}
```

## Browsing Flow Examples

### Example 1: General Hotel Search
**User Journey**: Home → Search "Miami" → View hotel list

**active_searches**:
```json
{
  "Miami": {
    "searchId": "search_abc123",
    "status": "cached",
    "destination": "Miami",
    "checkIn": "2025-02-01",
    "checkOut": "2025-02-05",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1, "childAges": []}
  }
}
```

**context_stack**:
```json
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  }
]
```

---

### Example 2: Drilling Into Rooms
**User Journey**: Hotel list → Click "View Rooms" on JW Marriott

**active_searches**:
```json
{
  "Miami": {
    "searchId": "search_abc123",
    "status": "cached",
    "destination": "Miami",
    "checkIn": "2025-02-01",
    "checkOut": "2025-02-05",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1, "childAges": []}
  },
  "Miami:JW Marriott": {
    "searchId": "rooms_def456",
    "status": "cached",
    "destination": "Miami",
    "hotel_id": "123abc",
    "hotel_name": "JW Marriott",
    "checkIn": "2025-02-01",
    "checkOut": "2025-02-05",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1, "childAges": []},
    "roomSearchId": "rooms_def456"
  }
}
```

**context_stack**:
```json
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  },
  {
    "type": "RoomList",
    "search_key": "Miami",
    "hotel_id": "123abc",
    "roomSearchId": "rooms_def456"
  }
]
```

**Note**: The base `HotelList` stays on the stack - user can "go back" to the hotel list.

---

### Example 3: Switching Between Hotels
**User Journey**: Viewing rooms at JW Marriott → Go back → View rooms at Hilton

**active_searches**:
```json
{
  "Miami": { /* ... same as before ... */ },
  "Miami:JW Marriott": { /* ... cached ... */ },
  "Miami:Hilton": {
    "searchId": "rooms_ghi789",
    "status": "cached",
    "destination": "Miami",
    "hotel_id": "456def",
    "hotel_name": "Hilton",
    "checkIn": "2025-02-01",
    "checkOut": "2025-02-05",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1, "childAges": []},
    "roomSearchId": "rooms_ghi789"
  }
}
```

**context_stack**:
```json
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  },
  {
    "type": "RoomList",
    "search_key": "Miami",
    "hotel_id": "456def",
    "roomSearchId": "rooms_ghi789"
  }
]
```

**Note**: The old `RoomList` (JW Marriott) is **popped and replaced** with the new one (Hilton). Only the most recent room view is kept on the stack.

---

### Example 4: Property-Specific Landing
**User Journey**: Clicks ad for JW Marriott → Lands on property-specific page

**active_searches**:
```json
{
  "Miami:JW Marriott": {
    "searchId": "rooms_xyz",
    "status": "cached",
    "destination": "Miami",
    "hotel_id": "123abc",
    "hotel_name": "JW Marriott",
    "checkIn": "2025-02-01",
    "checkOut": "2025-02-05",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1, "childAges": []},
    "roomSearchId": "rooms_xyz"
  }
}
```

**context_stack**:
```json
[
  {
    "type": "HotelDetails",
    "hotel_id": "123abc"
  },
  {
    "type": "RoomList",
    "search_key": "Miami:JW Marriott",
    "hotel_id": "123abc",
    "roomSearchId": "rooms_xyz"
  }
]
```

**Note**: When user lands directly on a property page, start with `HotelDetails` as the base instead of `HotelList`. This tells the agent the user is focused on this specific property.

---

### Example 5: User Initiates Booking
**User Journey**: Room list → Select "Deluxe King" → Click "Book Now" → Enter details

**active_searches**: (same as before)

**context_stack**:
```json
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  },
  {
    "type": "RoomList",
    "search_key": "Miami",
    "hotel_id": "123abc",
    "roomSearchId": "rooms_def456"
  },
  {
    "type": "BookingPending",
    "booking_hash": "booking_xyz",
    "session_id": "session_123",
    "payment_type": "phone",
    "hold_expires_at": "2025-01-14T12:00:00Z",
    "amount": 299.99,
    "s3_key": "bookings/xyz.json"
  }
]
```

**Note**: `BookingPending` is pushed on top. If user abandons and starts a new booking, the old `BookingPending` is replaced.

## Stack Management Rules

### Push Rules
1. **HotelList** - Pops any existing `HotelList`, `RoomList`, or `HotelDetails` from the top before pushing
2. **RoomList** - Pops any existing `RoomList` or `HotelDetails` from the top (keeps `HotelList` underneath)
3. **HotelDetails** - Can be pushed on top of anything (doesn't pop)
4. **BookingPending** - Replaces old `BookingPending` if one exists at the top

### Why HotelDetails Gets Popped

When pushing `HotelList` or `RoomList`, any `HotelDetails` at the top is automatically popped. This prevents stale detail contexts from accumulating when users switch focus:

**Example**: User views JW Marriott details → goes back → views Hilton rooms
- Stack before: `[HotelList(Miami), HotelDetails(JW Marriott)]`
- After pushing RoomList: `[HotelList(Miami), RoomList(Hilton)]` ✓ (HotelDetails was popped)

### Idempotency
If the exact same context is already at the top of the stack, **don't push it again**. Compare all fields (type + identifiers).

## Integration with active_searches

The `search_key` in context_stack contexts **must match a key** in `active_searches`:

- `HotelList` with `search_key: "Miami"` → `active_searches["Miami"]` must exist
- `RoomList` with `search_key: "Miami"` → `active_searches["Miami:JW Marriott"]` must exist (composite key)

The `search_key` acts as a label - the agent uses it to look up search metadata.

## Search Key Format

- **Hotel search**: `{destination}` (e.g., `"Miami"`)
- **Room search**: `{destination}:{hotel_name}` (e.g., `"Miami:JW Marriott"`)

## Understanding searchId and roomSearchId

### searchId
The `searchId` is a **Redis key** that cache-worker returns after processing a hotel or room search. It's used to retrieve cached search results from Redis.

**Format**:
- Hotel searches: `search:{hash}` (e.g., `"search_abc123"` → Redis key `search:abc123`)
- Room searches: `rooms:{hash}` (e.g., `"rooms_def456"` → Redis key `rooms:def456`)

**Source**: Cache-worker generates these when processing search requests and returns them in the API response. Store whatever cache-worker returns in the `searchId` field.

### roomSearchId
The `roomSearchId` is specifically for room searches and serves two purposes:
1. **Redis lookup key** - Used to query cached room data via `query_vfs` tool
2. **Unique identifier** - Hash of `hotel_id + checkIn + checkOut + occupancy`

**When to include**: Only present in `active_searches` entries for room searches (composite keys like `"Miami:JW Marriott"`), not for hotel-only searches.

**Example Flow**:
```
User searches hotels in Miami
→ Cache-worker processes and caches results
→ Returns: {"searchId": "search_abc123", ...}
→ Store in active_searches["Miami"]["searchId"]

User clicks "View Rooms" at JW Marriott
→ Cache-worker fetches and caches room data
→ Returns: {"roomSearchId": "rooms_def456", ...}
→ Store in active_searches["Miami:JW Marriott"]["roomSearchId"]
→ Also store in active_searches["Miami:JW Marriott"]["searchId"] (same value)
```

## Common Patterns

### Pattern 1: User browsing multiple destinations
Each destination gets its own `HotelList`. When user switches destinations, the entire stack is replaced:

```json
// User was viewing "Miami" → switches to "New York"
[
  {
    "type": "HotelList",
    "search_key": "New York"
  }
]
```

### Pattern 2: User comparing rooms at different hotels
Only the most recent `RoomList` is kept:

```json
// User viewing Hilton rooms (previously viewed JW Marriott)
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  },
  {
    "type": "RoomList",
    "search_key": "Miami",
    "hotel_id": "456def",  // Hilton
    "roomSearchId": "rooms_ghi789"
  }
]
```

### Pattern 3: User viewing hotel details without searching rooms
```json
[
  {
    "type": "HotelList",
    "search_key": "Miami"
  },
  {
    "type": "HotelDetails",
    "hotel_id": "123abc"
  }
]
```

## Reference

The context_stack logic is implemented in `/graphs/ava_v1/shared_libraries/context_helpers.py`. Refer to the `prepare_*_push()` functions for the exact push/pop rules used by the agent.
