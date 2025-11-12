"""Dynamic prompt customization based on runtime context."""
from ava.context import CallContext


def get_customized_prompt(call_context: CallContext = None) -> str:
    """
    Customize the agent prompt based on runtime context.

    This function generates a customized system prompt based on the call context type
    and associated data. It implements a priority system for handling multiple context types.

    Priority Order (highest to lowest):
    1. Abandoned Payment + Thread Continuation
    2. Property + Booking (hybrid)
    3. Property-Specific only
    4. Booking only
    5. Payment Return
    6. Session Context
    7. Thread Continuation
    8. General (default)

    Args:
        call_context: CallContext containing runtime context information

    Returns:
        Customized system prompt string
    """
    # Import the base prompt
    from ava.prompts.main_prompt import agent_instructions

    print(f"[Dynamic Prompt] get_customized_prompt called with context: {call_context}")

    # If no context provided or context is not a CallContext object, use default context
    if call_context is None or not isinstance(call_context, CallContext):
        print(f"[Dynamic Prompt] No valid context provided, using default prompt")
        return agent_instructions

    # Priority 1: Abandoned Payment (highest priority - proactive recovery)
    # This can combine with thread_continuation
    if call_context.abandoned_payment:
        print(f"[Dynamic Prompt] PRIORITY 1: Abandoned payment recovery - ${call_context.abandoned_payment.amount} ({call_context.abandoned_payment.minutes_ago}m ago)")
        from ava.prompts.abandoned_payment_prompt import get_abandoned_payment_prefix

        context_prefix = get_abandoned_payment_prefix(call_context.abandoned_payment)

        # Add thread continuation note if applicable
        if call_context.type == "thread_continuation" and call_context.thread_id:
            context_prefix += f"""

**Additional Context**: Thread continuation from {call_context.thread_id}
- You have access to the full conversation history
- Reference the previous booking attempt and conversation naturally
- The user was partway through completing this reservation

---

"""

        return context_prefix + agent_instructions

    # Priority 2: Property + Booking (hybrid - property context takes precedence but includes booking)
    if call_context.property and call_context.booking:
        print(f"[Dynamic Prompt] PRIORITY 2: Property + Booking hybrid - {call_context.property.property_name} with booking context")
        from ava.prompts.property_booking_prompt import get_property_booking_prompt
        return get_property_booking_prompt(call_context.property, call_context.booking)

    # Priority 3: Property-Specific only
    if call_context.type == "property_specific" and call_context.property:
        print(f"[Dynamic Prompt] PRIORITY 3: Property-specific only - {call_context.property.property_name}")
        from ava.prompts.property_specific_prompt import get_property_specific_prompt
        return get_property_specific_prompt(call_context.property)

    # Priority 4: Booking only
    if call_context.booking:
        print(f"[Dynamic Prompt] PRIORITY 4: Booking context only - {call_context.booking.destination}")
        from ava.prompts.booking_prompt import get_booking_context_prefix
        context_prefix = get_booking_context_prefix(call_context.booking)
        return context_prefix + agent_instructions

    # Priority 5: Payment Return
    if call_context.type == "payment_return" and call_context.payment:
        print(f"[Dynamic Prompt] PRIORITY 5: Payment return - {call_context.payment.status}")
        payment_data = call_context.payment

        # Enhanced payment return with transaction details
        context_prefix = f"""
**IMPORTANT CONTEXT**: The customer has just returned from payment processing.

**Payment Details**:
- Status: {payment_data.status}
- Amount: ${payment_data.amount} {payment_data.currency}
{f'- Transaction ID: {payment_data.transaction_id}' if payment_data.transaction_id else ''}
{f'- Timestamp: {payment_data.timestamp}' if payment_data.timestamp else ''}

**Your Approach**:
- Welcome the customer back warmly
- Confirm their payment status immediately
- If payment was successful: Congratulate them and provide next steps (confirmation email, check-in details)
- If payment failed: Empathize and offer to help retry or explore alternative options
- If payment is pending: Explain the status and what happens next
- Reference the transaction ID if they need to follow up
- Ask if there's anything else you can help with regarding their booking

---

"""
        return context_prefix + agent_instructions

    # Priority 6: Session Context (multi-leg call tracking)
    if call_context.session:
        print(f"[Dynamic Prompt] PRIORITY 6: Session context - {call_context.session.call_reference} ({len(call_context.session.session_legs)} legs)")
        session_data = call_context.session

        # Build session leg summary
        leg_types = [leg.leg_type for leg in session_data.session_legs]
        leg_summary = ", ".join(leg_types) if leg_types else "No legs recorded"

        context_prefix = f"""
**IMPORTANT CONTEXT**: Multi-leg call session.

**Session Details**:
- Call Reference: {session_data.call_reference}
- Session Legs: {len(session_data.session_legs)} ({leg_summary})
{f'- Previous Interactions: {len(session_data.previous_interactions)} recorded' if session_data.previous_interactions else ''}

**Your Approach**:
- This call may have been transferred or reconnected
- Be aware of potential context from previous call legs
- Maintain continuity across the session
- Reference previous interactions if the user mentions them
- Track that this is part of a larger call session

---

"""
        return context_prefix + agent_instructions

    # Priority 7: Thread Continuation
    if call_context.type == "thread_continuation" and call_context.thread_id:
        print(f"[Dynamic Prompt] PRIORITY 7: Thread continuation - {call_context.thread_id}")
        thread_id = call_context.thread_id
        context_prefix = f"""
**IMPORTANT CONTEXT**: This is a returning customer.

**Conversation Context**:
- Thread ID: {thread_id}
- This customer has interacted with you before

**Your Approach**:
- You have access to their full conversation history
- Reference previous interactions naturally when relevant
- Continue helping them where they left off
- Show recognition of their previous requests or bookings
- Maintain conversational continuity and build rapport

---

"""
        return context_prefix + agent_instructions

    # Priority 8: General (default/fallback)
    print(f"[Dynamic Prompt] PRIORITY 8: General/default context (type={call_context.type})")
    return agent_instructions
