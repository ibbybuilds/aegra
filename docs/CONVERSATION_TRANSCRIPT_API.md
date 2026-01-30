# Conversation Transcript API Documentation

## Executive Summary

This document describes how to retrieve full conversation transcripts between customers and the AVA hotel booking agent. These transcripts are critical for:

- **Chargeback Defense**: Providing evidence of customer consent and booking details
- **Dispute Resolution**: Reviewing what was communicated during the booking process
- **Audit Trail**: Maintaining records of customer interactions for compliance

### Key Concept: Thread ID = Correlation ID

In our CRM system, each booking has a `correlationId` field. **This correlationId is the same as the `thread_id`** in the conversation system. Use this ID to retrieve the full conversation transcript for any booking.

---

## Quick Start

### Retrieve Full Conversation Transcript

```bash
# Replace {thread_id} with the correlationId from your CRM booking record
curl -X POST https://api.example.com/threads/{thread_id}/history \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"limit": 1000}'
```

**Returns**: Complete conversation history including all messages, tool calls, and booking actions.

---

## API Endpoints

### 1. Get Full Conversation History

**Primary endpoint for retrieving complete transcripts.**

#### Endpoint
```
POST /threads/{thread_id}/history
GET /threads/{thread_id}/history
```

#### Use Case
- Retrieve complete conversation transcript for chargeback defense
- Export conversation history for auditing
- Review customer interactions for quality assurance

#### Request Parameters

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thread_id` | string | Yes | Thread ID (same as `correlationId` in CRM) |

**Request Body (POST method):**
```json
{
  "limit": 100,
  "before": "checkpoint_id_here",
  "metadata": {},
  "subgraphs": false,
  "checkpoint_ns": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `limit` | integer | No | 10 | Maximum number of checkpoints to return (1-1000) |
| `before` | string | No | null | Return checkpoints before this checkpoint ID (pagination) |
| `metadata` | object | No | {} | Filter checkpoints by metadata |
| `subgraphs` | boolean | No | false | Include subgraph states |
| `checkpoint_ns` | string | No | null | Checkpoint namespace filter |

**Query Parameters (GET method):**
```
GET /threads/{thread_id}/history?limit=100&subgraphs=false
```

#### Response Schema

**Status Code**: `200 OK`

**Response Body**: Array of `ThreadState` objects (newest first)

```json
[
  {
    "values": {
      "messages": [
        {
          "type": "human",
          "content": [{"type": "text", "text": "Hello"}],
          "id": "message-uuid",
          "additional_kwargs": {},
          "response_metadata": {}
        },
        {
          "type": "ai",
          "content": [{"type": "text", "text": "Hello! I'm Ava..."}],
          "id": "message-uuid",
          "tool_calls": [],
          "invalid_tool_calls": [],
          "usage_metadata": {
            "input_tokens": 15449,
            "output_tokens": 45,
            "total_tokens": 15494
          }
        },
        {
          "type": "ai",
          "content": [
            {"type": "text", "text": "Let me search for hotels..."},
            {
              "type": "tool_use",
              "id": "toolu_xxx",
              "name": "start_hotel_search",
              "input": {"destination": "Miami", "check_in": "2026-02-01"}
            }
          ],
          "tool_calls": [
            {
              "name": "start_hotel_search",
              "args": {
                "searches": [{
                  "destination": "Miami",
                  "check_in": "2026-02-01",
                  "check_out": "2026-02-02",
                  "occupancy": {"numOfAdults": 2, "numOfRooms": 1}
                }]
              },
              "id": "toolu_xxx",
              "type": "tool_call"
            }
          ]
        },
        {
          "type": "tool",
          "content": "{\"status\": \"success\", \"searchId\": \"abc123\"}",
          "name": "start_hotel_search",
          "tool_call_id": "toolu_xxx"
        }
      ],
      "customer_details": {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com"
      },
      "active_searches": {
        "Miami": {
          "searchId": "abc123",
          "status": "completed",
          "destination": "Miami",
          "checkIn": "2026-02-01",
          "checkOut": "2026-02-02"
        }
      }
    },
    "next": [],
    "tasks": [],
    "interrupts": [],
    "metadata": {
      "step": 119,
      "run_id": "run-uuid",
      "source": "loop",
      "user_id": "anonymous",
      "user_display_name": "Anonymous User"
    },
    "created_at": "2026-01-29T17:22:32.925492Z",
    "checkpoint": {
      "checkpoint_id": "checkpoint-uuid",
      "thread_id": "thread-uuid",
      "checkpoint_ns": ""
    },
    "parent_checkpoint": {
      "checkpoint_id": "parent-checkpoint-uuid",
      "thread_id": "thread-uuid",
      "checkpoint_ns": ""
    },
    "checkpoint_id": "checkpoint-uuid",
    "parent_checkpoint_id": "parent-checkpoint-uuid"
  }
]
```

#### Message Types

**1. Human Message** (Customer input)
```json
{
  "type": "human",
  "content": [{"type": "text", "text": "I want to book a hotel in Miami"}],
  "id": "message-uuid"
}
```

**2. AI Message** (Agent response)
```json
{
  "type": "ai",
  "content": [{"type": "text", "text": "I'll help you find hotels in Miami"}],
  "id": "message-uuid",
  "tool_calls": [],
  "usage_metadata": {
    "input_tokens": 1500,
    "output_tokens": 50
  }
}
```

**3. AI Message with Tool Call** (Agent taking action)
```json
{
  "type": "ai",
  "content": [
    {"type": "text", "text": "Let me search for available hotels"},
    {
      "type": "tool_use",
      "id": "toolu_xxx",
      "name": "book_room",
      "input": {
        "room": {
          "hotel_id": "hotel123",
          "rate_key": "rate456",
          "expected_price": 299.99
        },
        "payment_type": "phone"
      }
    }
  ],
  "tool_calls": [
    {
      "name": "book_room",
      "args": {/* tool arguments */},
      "id": "toolu_xxx"
    }
  ]
}
```

**4. Tool Result Message** (Result of agent action)
```json
{
  "type": "tool",
  "content": "{\"status\": \"payment_pending\", \"booking_hash\": \"abc123\"}",
  "name": "book_room",
  "tool_call_id": "toolu_xxx"
}
```

#### Error Responses

**404 Not Found**
```json
{
  "detail": "Thread 'thread-uuid' not found"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Error retrieving thread history: <error message>"
}
```

---

### 2. Get Current Thread State

**Get the latest checkpoint state for a conversation.**

#### Endpoint
```
GET /threads/{thread_id}/state
```

#### Use Case
- Check if a conversation is still active
- Get the most recent customer details and booking status
- Verify current state before taking action

#### Request Parameters

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thread_id` | string | Yes | Thread ID (correlationId) |

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `subgraphs` | boolean | No | false | Include subgraph states |
| `checkpoint_ns` | string | No | null | Checkpoint namespace |

#### Response Schema

**Status Code**: `200 OK`

**Response Body**: Single `ThreadState` object (same structure as history endpoint, but only the latest checkpoint)

```json
{
  "values": {
    "messages": [/* array of all messages */],
    "customer_details": {
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com"
    },
    "active_searches": {},
    "context_stack": []
  },
  "next": [],
  "tasks": [],
  "checkpoint": {
    "checkpoint_id": "latest-checkpoint-uuid",
    "thread_id": "thread-uuid"
  },
  "created_at": "2026-01-29T17:30:00Z"
}
```

---

### 3. Get Thread Metadata

**Get thread information and status.**

#### Endpoint
```
GET /threads/{thread_id}
```

#### Use Case
- Check if thread exists
- Verify thread ownership
- Get thread creation time and status

#### Request Parameters

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thread_id` | string | Yes | Thread ID (correlationId) |

#### Response Schema

**Status Code**: `200 OK`

```json
{
  "thread_id": "thread-uuid",
  "status": "idle",
  "metadata": {
    "owner": "anonymous",
    "assistant_id": "ava_v1",
    "graph_id": "ava_v1",
    "thread_name": ""
  },
  "user_id": "anonymous",
  "created_at": "2026-01-29T16:00:00Z"
}
```

**Status Values:**
- `idle`: Conversation inactive, ready for new messages
- `busy`: Agent is currently processing
- `interrupted`: Conversation paused (e.g., waiting for payment)
- `error`: An error occurred during processing

---

### 4. List All Runs for a Thread

**Get all execution runs (conversations) for a thread.**

#### Endpoint
```
GET /threads/{thread_id}/runs
```

#### Use Case
- See how many times the conversation was restarted
- Get execution metadata (start time, end time, status)
- Identify which run corresponds to the booking

#### Request Parameters

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thread_id` | string | Yes | Thread ID (correlationId) |

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 10 | Maximum number of runs to return |
| `offset` | integer | No | 0 | Number of runs to skip (pagination) |
| `status` | string | No | null | Filter by status (success, error, interrupted) |

#### Response Schema

**Status Code**: `200 OK`

```json
[
  {
    "run_id": "run-uuid",
    "thread_id": "thread-uuid",
    "assistant_id": "ava_v1",
    "status": "success",
    "input": {
      "messages": [{"type": "human", "content": "Hello"}]
    },
    "output": {
      "messages": [/* final message array */]
    },
    "config": {},
    "context": {},
    "user_id": "anonymous",
    "created_at": "2026-01-29T16:00:00Z",
    "updated_at": "2026-01-29T16:05:00Z",
    "error_message": null
  }
]
```

**Status Values:**
- `success`: Run completed successfully
- `error`: Run failed with an error
- `interrupted`: Run was interrupted (e.g., human-in-the-loop)
- `pending`: Run is waiting to start
- `running`: Run is currently executing

---

### 5. Get Specific Run Details

**Get details of a specific execution run.**

#### Endpoint
```
GET /threads/{thread_id}/runs/{run_id}
```

#### Use Case
- Get detailed execution metadata
- Review input and output for specific run
- Check error messages if run failed

#### Request Parameters

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `thread_id` | string | Yes | Thread ID (correlationId) |
| `run_id` | string | Yes | Run ID from list runs response |

#### Response Schema

**Status Code**: `200 OK`

```json
{
  "run_id": "run-uuid",
  "thread_id": "thread-uuid",
  "assistant_id": "ava_v1",
  "status": "success",
  "input": {
    "messages": [{"type": "human", "content": "I want to book a hotel"}]
  },
  "output": {
    "messages": [/* complete message history at end of run */]
  },
  "config": {
    "configurable": {
      "thread_id": "thread-uuid",
      "checkpoint_ns": ""
    }
  },
  "context": {},
  "user_id": "anonymous",
  "created_at": "2026-01-29T16:00:00Z",
  "updated_at": "2026-01-29T16:05:00Z",
  "error_message": null
}
```

---

## Use Case Examples

### Chargeback Defense Workflow

**Scenario**: A customer disputes a hotel booking charge. You need to prove they consented to the booking.

**Step 1: Locate the correlationId**
```
CRM Record → Booking → correlationId: "98bfc16e-c45a-4fb6-b6ae-2a2269eb7391"
```

**Step 2: Retrieve full conversation transcript**
```bash
curl -X POST https://api.example.com/threads/98bfc16e-c45a-4fb6-b6ae-2a2269eb7391/history \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"limit": 1000}'
```

**Step 3: Extract evidence from transcript**

Look for these key message types in the response:

1. **Customer provided personal details** (proves identity)
   ```json
   {
     "type": "tool",
     "name": "update_customer_details",
     "content": "{\"status\": \"success\", \"field\": \"email\", \"verified\": true}"
   }
   ```

2. **Customer confirmed hotel selection** (proves consent)
   ```json
   {
     "type": "human",
     "content": [{"text": "Yes, book that hotel"}]
   }
   ```

3. **Price was disclosed** (proves transparency)
   ```json
   {
     "type": "ai",
     "content": [{"text": "The total price is $299.99 per night"}]
   }
   ```

4. **Booking was initiated** (proves transaction)
   ```json
   {
     "type": "ai",
     "tool_calls": [{
       "name": "book_room",
       "args": {
         "room": {"expected_price": 299.99},
         "payment_type": "phone"
       }
     }]
   }
   ```

5. **Booking confirmation** (proves completion)
   ```json
   {
     "type": "tool",
     "name": "book_room",
     "content": "{\"status\": \"payment_pending\", \"booking_hash\": \"abc123\"}"
   }
   ```

**Step 4: Export for legal team**

Save the JSON response to a file:
```bash
curl -X POST https://api.example.com/threads/{thread_id}/history \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"limit": 1000}' > booking_transcript_case_12345.json
```

---

### Audit Trail Export

**Scenario**: Export all conversation transcripts for a specific date range.

```bash
# Step 1: List all threads created in date range
curl -X POST https://api.example.com/threads/search \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 100,
    "offset": 0,
    "order_by": "created_at DESC"
  }'

# Step 2: For each thread, retrieve history
for thread_id in $(cat threads.json | jq -r '.threads[].thread_id'); do
  curl -X POST https://api.example.com/threads/$thread_id/history \
    -H "Content-Type: application/json" \
    -d '{"limit": 1000}' > "transcript_$thread_id.json"
done
```

---

## Best Practices

### For Chargeback Defense

1. **Retrieve transcripts immediately when dispute is filed** - Don't wait, as conversations may be archived
2. **Look for explicit consent messages** - Search for phrases like "yes", "confirm", "book it"
3. **Document price disclosure** - Prove customer was shown the price before booking
4. **Verify customer identity** - Check that email/name was collected and verified
5. **Include timestamp evidence** - Use `created_at` fields to prove timeline

### For Technical Integration

1. **Set appropriate limit** - Use `limit: 1000` to ensure complete history retrieval
2. **Handle pagination** - Use `before` parameter if history exceeds limit
3. **Cache responses** - Store transcripts locally to avoid repeated API calls
4. **Filter tool calls** - Focus on `book_room`, `update_customer_details` tool calls for bookings
5. **Monitor rate limits** - Implement exponential backoff for large batch exports

### For Data Privacy

1. **Secure storage** - Encrypt transcripts at rest
2. **Access control** - Restrict access to authorized personnel only
3. **Retention policy** - Follow legal requirements for data retention
4. **Anonymization** - Consider redacting PII when sharing with non-legal teams
5. **Audit logging** - Log all transcript access for compliance

---

## Technical Reference

### Thread Lifecycle

```
1. Thread Created
   └─> status: "idle"

2. User sends message (Run created)
   └─> status: "busy"
   └─> Agent processes conversation
   └─> Creates checkpoints at each step

3. Booking initiated
   └─> status: "interrupted" (waiting for payment)
   └─> Checkpoint saved with booking details

4. Payment completed / Conversation ends
   └─> status: "idle"
   └─> Final checkpoint saved
```

### Checkpoint vs Run vs Thread

- **Thread**: The entire conversation container (correlationId)
- **Run**: A single execution of the agent (one interaction session)
- **Checkpoint**: A snapshot of state at a specific point in the conversation

**Relationship:**
```
Thread (1)
  ├─> Run 1 (2026-01-29 10:00)
  │     ├─> Checkpoint 1 (step 1)
  │     ├─> Checkpoint 2 (step 2)
  │     └─> Checkpoint 3 (step 3)
  └─> Run 2 (2026-01-29 10:30)
        ├─> Checkpoint 4 (step 1)
        └─> Checkpoint 5 (step 2)
```

### Data Retention

- Checkpoints are stored in PostgreSQL (LangGraph checkpointer)
- Full conversation history is preserved indefinitely by default
- Implement your own archival policy based on compliance requirements

---

## Troubleshooting

### "Thread not found" Error

**Problem**: API returns 404 when looking up thread by correlationId

**Solutions**:
1. Verify correlationId matches thread_id exactly (case-sensitive)
2. Check if thread exists: `GET /threads/{thread_id}`
3. Confirm thread wasn't deleted
4. Verify authentication token has access to this thread

### Empty History Response

**Problem**: API returns `[]` empty array

**Solutions**:
1. Check if any runs were executed: `GET /threads/{thread_id}/runs`
2. Verify thread has a graph_id: `GET /threads/{thread_id}`
3. Confirm checkpoints were created (check `created_at` in state)

### Incomplete Message History

**Problem**: Messages are missing or truncated

**Solutions**:
1. Increase `limit` parameter (max 1000)
2. Use pagination with `before` parameter
3. Check if multiple runs exist: `GET /threads/{thread_id}/runs`

### Tool Calls Not Showing Arguments

**Problem**: `tool_calls` array is empty or missing args

**Solutions**:
1. Check `content` array for `tool_use` type messages
2. Look for `partial_json` field in tool_use content
3. Verify the tool call completed (check for corresponding tool result message)

---

## Support

For technical questions or API access issues:
- **Technical Support**: dev@aegra.com
- **API Documentation**: https://docs.aegra.com
- **Status Page**: https://status.aegra.com

For legal/compliance questions regarding transcript usage:
- **Legal Team**: legal@aegra.com
