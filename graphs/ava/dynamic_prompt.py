"""Dynamic prompt customization based on runtime context."""
from ava.context import CallContext

def get_customized_prompt(call_context: CallContext = None) -> str:
    """
    Customize the agent prompt based on runtime context.

    This function generates a customized system prompt based on the call context type
    and associated data, which can be passed directly to create_deep_agent.

    Args:
        call_context: CallContext containing runtime context information

    Returns:
        Customized system prompt string
    """
    # Import the base prompt
    from ava.prompts.main_prompt import agent_instructions

    print(f"[Dynamic Prompt] get_customized_prompt called with context: {call_context}")

    # If no context provided or context is not a CallContext object, use default context (no modifications)
    if call_context is None or not isinstance(call_context, CallContext) or call_context.type == "general":
        print(f"[Dynamic Prompt] Using default prompt for context: {call_context}")
        print(f"[Dynamic Prompt] Default prompt tail (last 200 chars): {agent_instructions[-200:]}")
        return agent_instructions

    # Handle property-specific context with dedicated prompt
    if call_context.type == "property_specific" and call_context.property:
        print(f"[Dynamic Prompt] Building property_specific prompt for property: {call_context.property.property_name}")
        property_data = call_context.property
        
        # Import and use the property-specific prompt
        from ava.prompts.property_specific_prompt import get_property_specific_prompt
        return get_property_specific_prompt(property_data)

    # Build context-specific prefix for other context types
    context_prefix = ""

    if call_context.type == "payment_return" and call_context.payment:
        print(f"[Dynamic Prompt] Building payment_return prompt for payment: {call_context.payment.status}")
        payment_data = call_context.payment
        context_prefix = f"""
**IMPORTANT CONTEXT**: The customer has just returned from payment processing.

**Payment Status**:
- Status: {payment_data.status}
- Amount: ${payment_data.amount} {payment_data.currency}

**Your Approach**:
- Welcome the customer back warmly
- Confirm their payment status immediately
- If payment was successful: Congratulate them and provide next steps (confirmation email, check-in details)
- If payment failed: Empathize and offer to help retry or explore alternative options
- Ask if there's anything else you can help with regarding their booking
- Be prepared to answer questions about their reservation

---

"""

    elif call_context.type == "thread_continuation":
        print(f"[Dynamic Prompt] Building thread_continuation prompt for thread: {call_context.thread_id}")
        thread_id = call_context.thread_id or "continuing conversation"
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

    # Prepend the context-specific information to the base prompt
    final_prompt = context_prefix + agent_instructions
    
    # Debug: Print the tail of the instructions to see what's being used
    print(f"[Dynamic Prompt] Final prompt tail (last 200 chars): {final_prompt[-200:]}")
    
    return final_prompt
