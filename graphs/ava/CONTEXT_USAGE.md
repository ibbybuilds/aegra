# AVA Agent Context Configuration

This document explains how the AVA agent uses runtime context to customize its behavior based on the call scenario.

## Overview

The AVA agent now supports dynamic prompt customization based on runtime context passed from the server. This allows the agent to adapt its behavior and responses based on:

- **Property-specific inquiries**: When a customer is asking about a specific hotel
- **Payment returns**: When a customer returns from payment processing
- **Thread continuations**: When a customer returns to an existing conversation
- **General inquiries**: Default behavior for new conversations

## Architecture

### Components

1. **CallContext** ([context.py](./context.py)): Dataclass defining the structure of runtime context
2. **customize_agent_prompt** ([dynamic_prompt.py](./dynamic_prompt.py)): Dynamic prompt middleware that customizes the system prompt based on context
3. **Agent Configuration** ([graph.py](./graph.py)): Agent setup with context schema and middleware

### How It Works

```
HTTP Request → Server → Agent Invocation with Context → Dynamic Prompt → Customized Behavior
```

## Server Integration

### Request Format

When calling `/threads/{thread_id}/runs/stream`, include context in the request body:

```json
{
  "assistant_id": "booking_assistant",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Tell me about this hotel"
      }
    ]
  },
  "context": {
    "call_context": {
      "type": "property_specific",
      "property": {
        "property_id": "venetian_lv_001",
        "property_name": "The Venetian Las Vegas",
        "hotel_id": "vntian_lv",
        "location": "3355 S Las Vegas Blvd, Las Vegas, NV 89109",
        "features": ["Casino", "Grand Canal Shoppes", "Pool Complex", "Spa"]
      },
      "user_phone": "+1234567890",
      "thread_id": "thread_abc123"
    }
  },
  "config": {},
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

### Context Types

#### 1. Property-Specific Context

Use when the customer is inquiring about a specific property (e.g., from a landing page or ad).

```json
{
  "type": "property_specific",
  "property": {
    "property_id": "venetian_lv_001",
    "property_name": "The Venetian Las Vegas",
    "hotel_id": "vntian_lv",
    "location": "3355 S Las Vegas Blvd, Las Vegas, NV 89109",
    "features": ["Casino", "Grand Canal Shoppes", "Pool Complex", "Spa"]
  },
  "user_phone": "+1234567890"
}
```

**Agent Behavior**:
- Prioritizes information about the specific property
- Uses the hotel_id for immediate searches
- Highlights the property's unique features
- Provides enthusiastic but professional recommendations

#### 2. Payment Return Context

Use when the customer returns from payment processing.

```json
{
  "type": "payment_return",
  "payment": {
    "status": "success",
    "amount": 651.67,
    "currency": "USD"
  },
  "thread_id": "thread_abc123"
}
```

**Agent Behavior**:
- Welcomes the customer back
- Confirms payment status immediately
- Provides next steps (confirmation email, check-in details)
- Offers additional assistance

#### 3. Thread Continuation Context

Use when a customer returns to an existing conversation.

```json
{
  "type": "thread_continuation",
  "thread_id": "thread_abc123"
}
```

**Agent Behavior**:
- References previous interactions naturally
- Continues from where they left off
- Shows recognition of past requests
- Maintains conversational continuity

#### 4. General Context (Default)

Use for new conversations without specific context.

```json
{
  "type": "general"
}
```

**Agent Behavior**:
- Standard greeting and introduction
- Gathers requirements from scratch
- Guides through the hotel search process

## Server Implementation Example

Here's how the server should process the context:

```python
from ava.context import CallContext, PropertyInfo, PaymentInfo

async def invoke_ava_agent(request_data: dict):
    """Invoke the AVA agent with context from the request."""

    # Extract call_context from request
    call_context_data = request_data.get("context", {}).get("call_context", {})

    # Create CallContext instance
    if not call_context_data:
        # Default context
        call_context = CallContext(type="general")
    else:
        # Parse property info if present
        property_data = call_context_data.get("property")
        if property_data:
            property_info = PropertyInfo(
                property_id=property_data.get("property_id"),
                property_name=property_data.get("property_name"),
                hotel_id=property_data.get("hotel_id"),
                location=property_data.get("location"),
                features=property_data.get("features", [])
            )
        else:
            property_info = None

        # Parse payment info if present
        payment_data = call_context_data.get("payment")
        if payment_data:
            payment_info = PaymentInfo(
                status=payment_data.get("status"),
                amount=payment_data.get("amount"),
                currency=payment_data.get("currency")
            )
        else:
            payment_info = None

        # Create CallContext
        call_context = CallContext(
            type=call_context_data.get("type", "general"),
            property=property_info,
            payment=payment_info,
            user_phone=call_context_data.get("user_phone"),
            thread_id=call_context_data.get("thread_id")
        )

    # Invoke the agent with context
    result = await agent.ainvoke(
        request_data["input"],
        context=call_context
    )

    return result
```

## Testing

### Test Property-Specific Context

```bash
curl -X POST http://localhost:8000/threads/test_thread/runs/stream \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "ava",
    "input": {
      "messages": [{"role": "user", "content": "What are the amenities?"}]
    },
    "context": {
      "call_context": {
        "type": "property_specific",
        "property": {
          "property_id": "venetian_lv_001",
          "property_name": "The Venetian Las Vegas",
          "hotel_id": "vntian_lv",
          "location": "3355 S Las Vegas Blvd, Las Vegas, NV 89109",
          "features": ["Casino", "Grand Canal Shoppes"]
        }
      }
    }
  }'
```

### Test Payment Return Context

```bash
curl -X POST http://localhost:8000/threads/test_thread/runs/stream \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "ava",
    "input": {
      "messages": [{"role": "user", "content": "I'm back"}]
    },
    "context": {
      "call_context": {
        "type": "payment_return",
        "payment": {
          "status": "success",
          "amount": 651.67,
          "currency": "USD"
        },
        "thread_id": "test_thread"
      }
    }
  }'
```

## Benefits

1. **Context-Aware Responses**: The agent adapts its behavior based on the customer's journey
2. **Improved Conversion**: Property-specific context helps focus on the customer's interest
3. **Better UX**: Payment return handling provides immediate confirmation and guidance
4. **Continuity**: Thread continuation maintains conversation flow across sessions
5. **Flexibility**: Easy to add new context types as needed

## Future Enhancements

- Add more context types (e.g., special_offer, loyalty_member)
- Include user preferences in context (e.g., budget, preferred amenities)
- Add A/B testing support for different prompt strategies
- Implement context-based tool selection
