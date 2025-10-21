"""Context schema for AVA agent runtime configuration."""
from dataclasses import dataclass, field
from typing import Optional, NotRequired


@dataclass
class PropertyInfo:
    """Information about a specific property."""
    property_id: Optional[str] = None
    property_name: Optional[str] = None
    hotel_id: Optional[str] = None
    location: Optional[str] = None
    features: list[str] = field(default_factory=list)


@dataclass
class PaymentInfo:
    """Information about payment status."""
    status: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None


@dataclass
class CallContext:
    """
    Context information for the current conversation.

    This context is passed from the server when creating a new run.
    It contains metadata about the call context type and relevant data.
    """
    type: str = "general"  # property_specific, payment_return, thread_continuation, general
    property: Optional[PropertyInfo] = None
    payment: Optional[PaymentInfo] = None
    user_phone: Optional[str] = None
    thread_id: Optional[str] = None

    def __post_init__(self):
        """Convert dict to PropertyInfo/PaymentInfo if needed."""
        if isinstance(self.property, dict):
            self.property = PropertyInfo(**self.property)
        if isinstance(self.payment, dict):
            self.payment = PaymentInfo(**self.payment)
