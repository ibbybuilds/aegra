# Context Type Refactoring History

## 8-Type to 5-Type Consolidation

The context type system was recently refactored from **8 types to 5 types** for simplicity and clarity. This document provides historical context on what changed and why.

## Types That Were Consolidated

### `thread_continuation` → `general`

**Reason**: Thread continuation doesn't require special workflow handling. Whether it's a new conversation or continuing an existing one, the agent should follow the same logic based on what information is already in state. The presence of message history alone doesn't warrant a different prompt strategy.

**What Changed**:
- Threads with message history (len(messages) > 2) now auto-derive to `type="general"` instead of `type="thread_continuation"`
- No functional difference in agent behavior
- Simplified middleware auto-derivation logic

**Migration**: If you were explicitly setting `type="thread_continuation"`, change it to `type="general"`.

---

### `booking` → `general`

**Reason**: A booking context with just destination and dates (but no specific hotel) follows the exact same workflow as a general conversation. The agent collects any missing parameters and calls `start_hotel_search()`. There's no meaningful optimization or workflow difference to justify a separate type.

**What Changed**:
- Contexts with only `booking` object (no `property`) now map to `type="general"`
- Agent behavior is identical: collect destination/dates if missing → search hotels
- Auto-derivation treats booking-only contexts as general

**Migration**: If you were explicitly setting `type="booking"`, change it to `type="general"`.

---

### `property_booking_hybrid` → `dated_property` (Renamed)

**Reason**: The term "hybrid" was confusing and didn't clearly communicate the use case. `dated_property` better describes what it represents: a specific property with dates already known.

**What Changed**:
- Type name only (not functionality)
- All references in code updated to use `dated_property`
- Middleware auto-derivation uses new name

**Migration**: If you were explicitly setting `type="property_booking_hybrid"`, change it to `type="dated_property"`.

---

## Summary of Changes

| Old Type (8-Type System) | New Type (5-Type System) | Change Type |
|--------------------------|--------------------------|-------------|
| `abandoned_payment` | `abandoned_payment` | Unchanged |
| `property_booking_hybrid` | `dated_property` | Renamed |
| `property_specific` | `property_specific` | Unchanged |
| `payment_return` | `payment_return` | Unchanged |
| `booking` | `general` | Consolidated |
| `thread_continuation` | `general` | Consolidated |
| `general` | `general` | Unchanged |

**Benefits of Consolidation**:
- Simpler mental model for developers (5 types vs 8)
- Fewer edge cases to handle in middleware
- Clearer type names that describe the actual use case
- Maintains all functional workflow optimizations
- No loss of capability (the important distinctions remain)
- Easier to reason about which type to use

**No Breaking Changes**: The middleware auto-derivation logic was updated to use the new 5-type system, so existing conversations continue to work correctly. Only explicit type assignments in API calls need to be updated.

---

Last Updated: 2026-01-30
