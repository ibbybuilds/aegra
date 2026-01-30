# Chargeback Defense Quick Reference Guide

## For Legal & Customer Service Teams

This guide explains how to retrieve conversation transcripts when customers dispute hotel bookings.

---

## What You Need to Know

### The Correlation ID

Every hotel booking in our CRM has a **correlationId** field. This ID is the key to retrieving the full conversation transcript.

**Example:**
```
Booking #12345
├─ Customer: John Doe
├─ Hotel: Miami Beach Resort
├─ Amount: $299.99
└─ correlationId: 98bfc16e-c45a-4fb6-b6ae-2a2269eb7391  ← Use this!
```

---

## How to Retrieve a Transcript

### Option 1: Self-Service (Technical Users)

If you have API access, use this command:

```bash
curl -X POST https://api.aegra.com/threads/{correlationId}/history \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000}' > transcript.json
```

Replace `{correlationId}` with the ID from the CRM booking.

### Option 2: Request from Engineering

Send an email to **dev@aegra.com** with:

**Subject:** Transcript Request - Case #{case_number}

**Body:**
```
Case Number: #12345
Booking correlationId: 98bfc16e-c45a-4fb6-b6ae-2a2269eb7391
Customer Name: John Doe
Booking Date: 2026-01-29
Reason: Chargeback dispute
```

Engineering will provide the transcript within 24 hours.

---

## What's in the Transcript

The transcript contains a complete record of the conversation, including:

### 1. Customer Identity Verification
- Name provided by customer
- Email address provided
- Phone number (if applicable)

**What to look for:**
```json
"customer_details": {
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com"
}
```

### 2. Hotel Search Parameters
- Where the customer wanted to stay
- Check-in and check-out dates
- Number of guests

**What to look for:**
```json
"active_searches": {
  "Miami": {
    "destination": "Miami",
    "checkIn": "2026-02-01",
    "checkOut": "2026-02-02",
    "occupancy": {"numOfAdults": 2, "numOfRooms": 1}
  }
}
```

### 3. Customer Messages
- Every message the customer typed
- Timestamps for each message

**What to look for:**
```json
{
  "type": "human",
  "content": [{"text": "Yes, book that hotel for me"}],
  "id": "message-uuid"
}
```

### 4. Price Disclosure
- Prices shown to customer
- Price confirmations

**What to look for in AI messages:**
```json
{
  "type": "ai",
  "content": [{"text": "The total price is $299.99 per night"}]
}
```

### 5. Booking Confirmation
- Exact moment booking was initiated
- Payment details
- Booking reference

**What to look for:**
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

---

## Building Your Chargeback Defense

### Evidence Checklist

When reviewing a transcript for chargeback defense, verify:

- [ ] **Customer provided their real name**
  - Look in `customer_details.first_name` and `customer_details.last_name`

- [ ] **Customer provided their real email**
  - Look in `customer_details.email`
  - Cross-reference with payment records

- [ ] **Customer explicitly requested the booking**
  - Look for human messages saying "yes", "book it", "confirm"

- [ ] **Price was disclosed before booking**
  - Look for AI messages mentioning the price
  - Timestamp should be BEFORE booking confirmation

- [ ] **Customer confirmed the price**
  - Look for human message after price disclosure
  - Should contain affirmative response

- [ ] **Booking was completed**
  - Look for `book_room` tool call
  - Look for success status in tool result

### Red Flags to Watch For

⚠️ **Weak cases** (customer may have valid dispute):
- No explicit price disclosure in transcript
- Customer asked to cancel but booking proceeded
- System error messages visible in transcript
- Customer expressed confusion about pricing

✅ **Strong cases** (transcript supports business):
- Clear price disclosure
- Explicit customer confirmation ("yes, book it")
- Customer provided personal details willingly
- No error messages or technical issues

---

## Example: Strong Chargeback Defense

Here's an example of what a strong defense looks like:

### Timeline from Transcript:

**10:00:00 AM** - Customer: "I want to book a hotel in Miami"
```json
{"type": "human", "content": [{"text": "I want to book a hotel in Miami"}]}
```

**10:00:15 AM** - Agent: "What's your name?"
```json
{"type": "ai", "content": [{"text": "What's your name?"}]}
```

**10:00:30 AM** - Customer: "John Doe"
```json
{"type": "human", "content": [{"text": "John Doe"}]}
```

**10:02:00 AM** - Agent: "The Marriott is $299.99 per night. Would you like to book it?"
```json
{"type": "ai", "content": [{"text": "The Marriott is $299.99 per night. Would you like to book it?"}]}
```

**10:02:15 AM** - Customer: "Yes, book it"
```json
{"type": "human", "content": [{"text": "Yes, book it"}]}
```

**10:02:20 AM** - System: Booking initiated
```json
{"type": "ai", "tool_calls": [{"name": "book_room", "args": {"expected_price": 299.99}}]}
```

### Defense Statement:

> "Our records show that on January 29, 2026 at 10:00 AM, the customer initiated a conversation with our automated booking agent. The customer:
>
> 1. Provided their name as 'John Doe' (10:00:30 AM)
> 2. Was shown the price of $299.99 per night (10:02:00 AM)
> 3. Explicitly confirmed the booking by stating 'Yes, book it' (10:02:15 AM)
> 4. The booking was completed at 10:02:20 AM
>
> Attached is the complete conversation transcript showing the customer's voluntary participation and explicit consent to the transaction."

---

## Frequently Asked Questions

### Q: How far back can we retrieve transcripts?

**A:** Transcripts are retained indefinitely. As long as you have the correlationId, you can retrieve the conversation.

### Q: What if the correlationId doesn't return a transcript?

**A:** This could mean:
1. The ID is incorrect (double-check CRM)
2. The booking never completed a conversation
3. The thread was deleted (rare, requires manual intervention)

Contact engineering immediately if you encounter this during a dispute.

### Q: Can customers claim the transcript is fabricated?

**A:** No. Each message has:
- Unique ID (cryptographically secure)
- Timestamp (server-generated, immutable)
- Checkpoint ID (blockchain-like chain of events)

The system is tamper-proof and provides a verifiable audit trail.

### Q: What if the customer says they didn't type those messages?

**A:** The transcript only proves that someone using the customer's contact information completed the booking. You'll need to:
1. Cross-reference with payment authorization records
2. Check IP address logs (contact engineering)
3. Verify the phone number used for payment transfer
4. Check if customer reported unauthorized access

### Q: Can we share transcripts with customers?

**A:** Yes, but redact sensitive information:
- ✅ Keep: customer's own messages, timestamps, prices
- ❌ Redact: system internals, tool call details, checkpoint IDs

Provide a human-readable summary rather than raw JSON when possible.

### Q: How do I read the JSON format?

**A:** The transcript is in JSON format (technical data format). Key fields:

- `"type": "human"` = Customer message
- `"type": "ai"` = Agent response
- `"content"` = The actual message text
- `"created_at"` = When it happened

For a readable version, ask engineering to generate a "plain English" transcript.

---

## Need Help?

### For Urgent Disputes (Chargeback Deadline < 48 hours)
**Contact:** urgent@aegra.com
**Subject:** URGENT: Chargeback Case #{case_number}

### For Regular Transcript Requests
**Contact:** dev@aegra.com
**Expected Response:** Within 24 hours

### For Legal Questions
**Contact:** legal@aegra.com

---

## Quick Reference Commands

### Get Full Transcript
```bash
curl -X POST https://api.aegra.com/threads/{correlationId}/history \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000}'
```

### Check if Thread Exists
```bash
curl https://api.aegra.com/threads/{correlationId} \
  -H "Authorization: Bearer YOUR_KEY"
```

### Get Just Customer Details
```bash
curl https://api.aegra.com/threads/{correlationId}/state \
  -H "Authorization: Bearer YOUR_KEY" \
  | jq '.values.customer_details'
```

---

## Document Version

**Last Updated:** 2026-01-29
**Maintained By:** Engineering Team
**Review Schedule:** Quarterly
