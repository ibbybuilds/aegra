"""Context parsing utilities for different graph types."""
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def parse_ava_context(context_dict: Optional[dict[str, Any]]) -> Any:
    """
    Parse request context for the AVA agent.

    Args:
        context_dict: Raw context dictionary from the API request

    Returns:
        CallContext instance for AVA agent, or None if no context provided
    """
    print(f"[AVA Context] Starting parse_ava_context with context_dict={context_dict}")
    
    if not context_dict:
        # Import here to avoid circular dependencies
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "graphs"))
        from ava.context import CallContext
        print("[AVA Context] No context provided, using general context")
        return CallContext(type="general")

    # Extract call_context from the request context
    call_context_data = context_dict.get("call_context", {})

    if not call_context_data:
        # Default to general context
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "graphs"))
        from ava.context import CallContext
        print("[AVA Context] No call_context in request, using general context")
        return CallContext(type="general")

    # Import AVA context classes
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "graphs"))
    from ava.context import CallContext, PropertyInfo, PaymentInfo

    # Parse property info if present
    property_data = call_context_data.get("property")
    if property_data and isinstance(property_data, dict):
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
    if payment_data and isinstance(payment_data, dict):
        payment_info = PaymentInfo(
            status=payment_data.get("status"),
            amount=payment_data.get("amount"),
            currency=payment_data.get("currency")
        )
    else:
        payment_info = None

    # Create CallContext
    context_type = call_context_data.get("type", "general")
    call_context = CallContext(
        type=context_type,
        property=property_info,
        payment=payment_info,
        user_phone=call_context_data.get("user_phone"),
        thread_id=call_context_data.get("thread_id")
    )

    # Log the parsed context details
    log_parts = [f"[AVA Context] Parsed context type: {context_type}"]

    if property_info:
        log_parts.append(f"property={property_info.property_name} (hotel_id={property_info.hotel_id})")

    if payment_info:
        log_parts.append(f"payment={payment_info.status} (${payment_info.amount} {payment_info.currency})")

    if call_context.user_phone:
        log_parts.append(f"phone={call_context.user_phone}")

    if call_context.thread_id:
        log_parts.append(f"thread={call_context.thread_id}")

    print(" | ".join(log_parts))

    return call_context


def parse_context_for_graph(graph_id: str, context_dict: Optional[dict[str, Any]]) -> Any:
    """
    Parse context based on the graph type.

    Args:
        graph_id: The graph identifier (e.g., "ava", "react_agent")
        context_dict: Raw context dictionary from the API request

    Returns:
        Parsed context appropriate for the graph type
    """
    print(f"[Context Parser] Parsing context for graph_id={graph_id}")

    # Map graph IDs to their context parsers
    if graph_id == "ava":
        return parse_ava_context(context_dict)

    # For other graphs, return the raw context dict or None
    # This maintains backward compatibility with graphs that don't use context schemas
    print(f"[Context Parser] No custom parser for graph_id={graph_id}, passing through raw context")
    return context_dict
