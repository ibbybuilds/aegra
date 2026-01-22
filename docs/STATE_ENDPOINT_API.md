# /state Endpoint API Reference

## Overview

The `/state` endpoint allows pre-initializing thread state and context before the first agent run. This is critical for implementing different conversation entry points and workflow optimizations.

## Endpoint

```
POST /threads/{thread_id}/state
```

## Request Model

```typescript
{
  "values": {                    // Optional: Initial state values
    "active_searches": {...},
    "search_params": {...},
    "customer_details": {...}
  },
  "context": {                   // Optional: Call context for dynamic prompts
    "type": "property_specific",
    "property": {...},
    "booking": {...},
    // ... other context fields
  },
  "checkpoint_id": "...",        // Optional: Specific checkpoint
  "checkpoint_ns": "...",        // Optional: Checkpoint namespace
  "checkpoint": {...}            // Optional: Checkpoint config
}
```

## Context Structure

### Base CallContext Fields

```typescript
{
  "type": string,                         // Context type (see types below)
  "property": PropertyInfo | null,        // Hotel/property information
  "payment": PaymentInfo | null,          // Payment status information
  "session": CallSessionContext | null,   // Multi-leg session data
  "booking": DialMapBookingContext | null,// Dial map booking data
  "abandoned_payment": AbandonedPaymentContext | null,  // Recovery data
  "user_phone": string | null,            // E.164 format phone
  "thread_id": string | null,             // Thread identifier
  "call_reference": string | null,        // Call tracking ID
  "dial_map_session_id": string | null    // Dial map session ID
}
```

## Context Types & Priority Mapping

The `type` field determines which priority level and prompt template will be used:

| Type | Priority | Template | Use Case |
|------|----------|----------|----------|
| `abandoned_payment` | 1 | abandoned_payment / abandoned_payment_with_thread | Payment recovery flows |
| `dated_property` | 2 | dated_property | Hotel page with dates pre-filled |
| `property_specific` | 3 | ga_call_extension | Hotel page without dates (GA clicks) |
| `payment_return` | 4 | payment_return | Post-payment confirmation |
| `general` | 5 | general | Homepage, no specific context |

**Note**: The actual priority is determined by `template.py::_determine_priority()` which checks for the **presence of objects** (e.g., `context.property` and `context.booking`), not just the type string. However, setting the correct type ensures consistency.

## Nested Object Schemas

### PropertyInfo

```typescript
{
  "property_name": string,  // e.g., "JW Marriott Miami"
  "hotel_id": string       // e.g., "123abc"
}
```

### DialMapBookingContext

```typescript
{
  "destination": string,    // e.g., "Miami"
  "check_in": string,       // YYYY-MM-DD format
  "check_out": string,      // YYYY-MM-DD format
  "rooms": number,          // Default: 1
  "adults": number,         // Default: 2
  "children": number,       // Default: 0
  "hotel_id": string | null // Optional hotel ID
}
```

### AbandonedPaymentContext

```typescript
{
  "timestamp": string,      // ISO 8601 format
  "amount": number,         // e.g., 299.99
  "currency": string,       // e.g., "USD"
  "minutes_ago": number,    // Time since abandonment
  "reason": string | null   // e.g., "timeout", "user_cancelled"
}
```

### PaymentInfo

```typescript
{
  "status": string,         // e.g., "completed", "failed", "pending"
  "amount": number,
  "currency": string,
  "transaction_id": string | null,
  "timestamp": string | null
}
```

### CallSessionContext

```typescript
{
  "call_reference": string,
  "session_legs": SessionLeg[],
  "previous_interactions": object[]
}
```

## Usage Examples

### Example 1: General Entry Point (Homepage)

**Scenario**: User lands on homepage, no context available

```json
POST /threads/{thread_id}/state
{
  "context": {
    "type": "general"
  }
}
```

**Agent Behavior**:
- Greets user
- Asks for destination
- Asks for dates → calls `update_search_params`
- Asks for occupancy → calls `update_search_params`
- Confirms all parameters
- Calls `start_hotel_search` with full parameters
- Presents top 3 hotel options

---

### Example 2: Property-Specific Entry (GA Call Extension)

**Scenario**: User clicks Google Ad for "JW Marriott Miami"

```json
POST /threads/{thread_id}/state
{
  "context": {
    "type": "property_specific",
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    }
  }
}
```

**Agent Behavior**:
- Acknowledges hotel: "I can help you book at JW Marriott Miami"
- Asks for dates → calls `update_search_params(checkIn)`, `update_search_params(checkOut)`
- Asks for occupancy → calls `update_search_params(numOfAdults)`, etc.
- Confirms parameters
- Calls `start_room_search(hotel_id="123abc")` directly (NO hotel_search)
- Presents room options

**Optimization**: Skips hotel search API call

---

### Example 3: Dated Property Entry

**Scenario**: User clicks "Book Now" on hotel page with dates already selected

```json
POST /threads/{thread_id}/state
{
  "context": {
    "type": "dated_property",
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    },
    "booking": {
      "destination": "Miami",
      "check_in": "2026-02-01",
      "check_out": "2026-02-03",
      "rooms": 1,
      "adults": 2,
      "children": 0
    }
  }
}
```

**Agent Behavior**:
- Acknowledges hotel + dates: "I see you're interested in JW Marriott Miami for February 1-3"
- Asks for occupancy (if not provided) → calls `update_search_params` only for missing fields
- Confirms parameters
- Calls `start_room_search(hotel_id="123abc")` directly (NO hotel_search)
- Presents room options

**Optimization**: Skips hotel search + fewer questions (dates already known)

---

### Example 4: Abandoned Payment Recovery

**Scenario**: Customer started booking but didn't complete payment (10 minutes ago)

```json
POST /threads/{thread_id}/state
{
  "context": {
    "type": "abandoned_payment",
    "abandoned_payment": {
      "timestamp": "2026-01-22T10:15:00Z",
      "amount": 299.99,
      "currency": "USD",
      "minutes_ago": 10,
      "reason": "timeout"
    },
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    }
  }
}
```

**Agent Behavior**:
- Acknowledges abandoned payment immediately: "I see you were in the process of booking a room for $299.99..."
- Proactively offers to complete: "I can help you complete that booking right now..."
- Creates urgency: "I can help you complete this right away..."
- Streamlines process to minimize friction
- References previous booking attempt details

**Optimization**: Recovery-focused flow with urgency

---

### Example 5: Payment Return Confirmation

**Scenario**: Customer redirected after Stripe payment (successful)

```json
POST /threads/{thread_id}/state
{
  "context": {
    "type": "payment_return",
    "payment": {
      "status": "completed",
      "amount": 299.99,
      "currency": "USD",
      "transaction_id": "txn_abc123",
      "timestamp": "2026-01-22T10:25:00Z"
    },
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    }
  }
}
```

**Agent Behavior**:
- Confirms payment: "Welcome back! I'm happy to confirm your payment was successful..."
- Provides next steps: "You should receive a confirmation email within 5 minutes..."
- Offers assistance: "Is there anything else I can help you with?"

**Optimization**: Confirmation-focused flow, no booking needed

---

### Example 6: Combined State and Context

**Scenario**: Pre-populate both state values AND context

```json
POST /threads/{thread_id}/state
{
  "values": {
    "search_params": {
      "checkIn": "2026-02-01",
      "checkOut": "2026-02-03",
      "numOfAdults": 2,
      "numOfRooms": 1
    },
    "customer_details": {
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com"
    }
  },
  "context": {
    "type": "property_specific",
    "property": {
      "property_name": "JW Marriott Miami",
      "hotel_id": "123abc"
    },
    "user_phone": "+12125551234"
  }
}
```

**Agent Behavior**:
- Has all information pre-loaded
- Can skip directly to room search
- Customer details already collected
- Fastest path to booking

---

## Context Derivation (Auto-Detection)

If explicit context is NOT provided via `/state`, the middleware will **auto-derive** context from the agent's state:

### Auto-Derivation Logic

```python
# Priority order:
1. Explicit context (via /state or /runs endpoint)
   └─ Use provided context as-is

2. Auto-derive from state.active_searches:
   ├─ hotel_id + booking_info → type="dated_property"
   ├─ hotel_id only → type="property_specific"
   └─ booking_info only → type="general"

3. Message history check:
   └─ len(messages) > 2 → type="general"

4. Default:
   └─ type="general"
```

### Example Auto-Derivation Scenarios

**Scenario 1**: Agent calls `start_hotel_search` → Creates active_searches entry
```json
// State after start_hotel_search:
{
  "active_searches": {
    "Miami": {
      "searchId": "abc123",
      "destination": "Miami",
      "checkIn": "2026-02-01",
      "checkOut": "2026-02-03"
      // ... other fields
    }
  }
}

// Middleware derives: type="general" (no hotel_id in context)
```

**Scenario 2**: State initialized with hotel_id in context_stack
```json
// State:
{
  "context_stack": [
    {
      "type": "HotelDetails",
      "hotel_id": "123abc",
      "hotel_name": "JW Marriott"
    }
  ]
}

// Middleware derives: type="property_specific"
```

---

## Response

### Success Response (200 OK)

```json
{
  "checkpoint": {
    "checkpoint_id": "1ef...",
    "checkpoint_ns": "",
    "thread_id": "abc123",
    // ... other checkpoint fields
  }
}
```

### Error Responses

**404 Not Found**
```json
{
  "detail": "Thread 'abc123' not found"
}
```

**400 Bad Request**
```json
{
  "detail": "Thread 'abc123' has no associated graph. Cannot update state."
}
```

**500 Internal Server Error**
```json
{
  "detail": "Failed to load graph 'ava_v1': ..."
}
```

---

## Implementation Details

### Context Format Compatibility

The context parser handles **two formats** for backward compatibility:

**Format 1 (NEW /state endpoint)**: Direct context
```json
{
  "context": {
    "type": "property_specific",
    "property": {...}
  }
}
```

**Format 2 (OLD /runs endpoint)**: Nested call_context
```json
{
  "context": {
    "call_context": {
      "type": "property_specific",
      "property": {...}
    }
  }
}
```

Both formats are automatically handled by `context_parser.py`.

### State Injection

For `ava` and `ava_v1` graphs, the parsed context is automatically injected into state as `call_context`:

```python
# After parsing, state will contain:
{
  "call_context": {
    "type": "property_specific",
    "property": PropertyInfo(...),  # Auto-converted to dataclass
    // ...
  }
}
```

Nested dicts are automatically converted to typed dataclass instances via `CallContext.__post_init__()`.

---

## Best Practices

### 1. Set Context Before First Run

Always call `/state` **before** the first message to ensure the agent uses the correct prompt from the start.

```python
# Good: Set context first
POST /threads/{thread_id}/state  # Set context
POST /threads/{thread_id}/runs   # Start conversation

# Bad: Context after first message
POST /threads/{thread_id}/runs   # Uses general prompt
POST /threads/{thread_id}/state  # Too late, first message already sent
```

### 2. Provide Complete Context

Include all relevant fields to maximize optimization:

```json
// Complete context enables maximum workflow shortcuts
{
  "type": "dated_property",
  "property": {
    "property_name": "JW Marriott Miami",
    "hotel_id": "123abc"
  },
  "booking": {
    "destination": "Miami",
    "check_in": "2026-02-01",
    "check_out": "2026-02-03",
    "rooms": 1,
    "adults": 2,
    "children": 0
  },
  "user_phone": "+12125551234"  // Enables SMS payment
}
```

### 3. Match Type to Objects

Ensure the `type` field matches the objects provided:

- `property_specific` → Provide `property` only
- `dated_property` → Provide both `property` AND `booking`
- `abandoned_payment` → Provide `abandoned_payment` (and optionally `property`)
- `payment_return` → Provide `payment` (and optionally `property`)

### 4. Use Correct Date Format

Always use ISO 8601 for timestamps and YYYY-MM-DD for dates:

```json
{
  "booking": {
    "check_in": "2026-02-01",    // ✓ Correct
    "check_out": "2/3/2026"      // ✗ Wrong - will fail validation
  },
  "abandoned_payment": {
    "timestamp": "2026-01-22T10:25:00Z"  // ✓ Correct ISO 8601
  }
}
```

### 5. Pre-populate Customer Details When Available

If you already have customer information (e.g., from account profile), include it in `values`:

```json
{
  "values": {
    "customer_details": {
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com"
    }
  },
  "context": {
    "type": "property_specific",
    "property": {...}
  }
}
```

This skips the customer info collection steps entirely.

---

## Monitoring & Debugging

### Enable Context Logging

Context parsing and priority determination are logged at INFO level:

```
[CONTEXT_MIGRATION] Context provided in /state request
[CONTEXT_MIGRATION] Raw context type: property_specific
[CONTEXT_MIGRATION] ✓ Successfully parsed context for graph ava_v1
[CONTEXT_AUTO_DERIVE] Auto-derived type: dated_property (hotel_id=123abc, dates present)
```

### Check Priority Assignment

The middleware logs which priority was determined:

```python
# In middleware.py::customize_agent_prompt()
logger.info(f"Using priority: {priority}")
```

### Verify State After Update

Query the state to verify context was set correctly:

```
GET /threads/{thread_id}/state
```

Response will include `call_context` in the state values.

---

## Related Documentation

- [AVA Prompt Architecture](./AVA_PROMPT_ARCHITECTURE.md) - Priority system and workflow optimization
- [CLAUDE.md](../CLAUDE.md) - Development patterns and examples
- [context.py](../graphs/ava_v1/context.py) - CallContext dataclass definition
- [template.py](../graphs/ava_v1/prompts/template.py) - Priority determination logic
- [middleware.py](../graphs/ava_v1/middleware.py) - Context extraction and auto-derivation

---

**Last Updated**: January 22, 2026
