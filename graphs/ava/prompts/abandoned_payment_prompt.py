"""Abandoned payment context prompt for proactive recovery."""
from ava.context import AbandonedPaymentContext


def get_abandoned_payment_prefix(abandoned_payment: AbandonedPaymentContext) -> str:
    """
    Generate context prefix for abandoned payment recovery.

    This handles cases where a customer was in the middle of completing
    a booking payment but the call was dropped, timed out, or interrupted.

    Args:
        abandoned_payment: The abandoned payment context with amount, time, reason

    Returns:
        Context prefix to prepend to the main agent prompt
    """
    # Format the amount nicely
    amount_str = f"${abandoned_payment.amount:.2f} {abandoned_payment.currency}"

    # Determine the appropriate language based on reason and time
    if abandoned_payment.reason == "dropped":
        reason_context = "the call was unexpectedly dropped"
        recovery_phrase = "I apologize for the disconnection"
    elif abandoned_payment.reason == "timeout":
        reason_context = "the payment session timed out"
        recovery_phrase = "I understand the payment process took longer than expected"
    else:
        reason_context = "we were interrupted"
        recovery_phrase = "I see we got disconnected"

    # Time-based urgency
    if abandoned_payment.minutes_ago < 5:
        time_context = "just a moment ago"
        urgency = "We can pick up right where we left off."
    elif abandoned_payment.minutes_ago < 15:
        time_context = f"about {abandoned_payment.minutes_ago} minutes ago"
        urgency = "Your reservation details are still available."
    else:
        time_context = f"about {abandoned_payment.minutes_ago} minutes ago"
        urgency = "I'll need to verify the room is still available, but I can help you complete this booking."

    return f"""
**CRITICAL CONTEXT - ABANDONED PAYMENT RECOVERY**: This customer was in the middle of completing a booking payment when {reason_context}.

**Abandoned Payment Details**:
- Amount: {amount_str}
- Time Elapsed: {abandoned_payment.minutes_ago} minutes
- Reason: {abandoned_payment.reason}
- Timestamp: {abandoned_payment.timestamp}

## YOUR APPROACH - PROACTIVE RECOVERY

### Opening (REQUIRED - Start with this immediately)
You MUST proactively acknowledge the interrupted booking:

1. **Acknowledge the situation**: "{recovery_phrase}. Welcome back!"
2. **Reference the booking**: "I see we were in the middle of completing your reservation for {amount_str}."
3. **Offer to continue**: "{urgency} Would you like me to help you complete this booking?"

### Example Opening Script:
"Welcome back! {recovery_phrase}. I see we were in the middle of completing your reservation for {amount_str} {time_context}. {urgency} Would you like me to help you complete this booking, or would you prefer to make any changes?"

### Recovery Options

**Option 1: Complete Original Booking** (Preferred)
- Verify the room/rate is still available
- Resume the payment process with the same details
- Expedite the process - they've already made their decision once
- Use phrases like: "Let me check if that room is still available" or "I can get you back to payment in just a moment"

**Option 2: Modify Booking**
- If they want to change details (dates, room type, etc.)
- Start a new search with their requirements
- Explain: "No problem, let me help you find something that works better"

**Option 3: Start Fresh**
- If they want to explore other options entirely
- Treat as a new booking search
- Reference their previous interest: "I understand you were looking at options around {amount_str}. What can I help you find today?"

### Behavioral Guidelines

**Priority**: Recovery first, then qualification
- Don't immediately jump into standard qualification questions
- Address the abandoned booking FIRST in your initial response
- Show empathy for the interruption
- Build confidence that you can complete this quickly

**Empathy & Trust**:
- Acknowledge the inconvenience sympathetically
- Express understanding of any frustration
- Reassure them you have their previous information
- Make the process as smooth as possible

**Efficiency**:
- They've already invested time in this booking
- Minimize redundant questions
- Fast-track to completion if they want to proceed
- Reference conversation history from the thread

**Call-to-Action**:
- Create gentle urgency: "Let's secure this before the rate changes"
- Emphasize simplicity: "We can have you booked in just a couple minutes"
- Offer confidence: "I'll make sure we get this completed smoothly this time"

### Voice Optimization
- Use warm, understanding tone
- Brief responses (max 4 lines after acknowledgment)
- Natural conversation appropriate for phone calls
- No special characters or formatting symbols

### CRITICAL RULE
**You MUST address the abandoned payment in your very first response**. Do not wait for the user to mention it. This is proactive recovery - acknowledge it immediately and offer to help complete the booking.
"""
