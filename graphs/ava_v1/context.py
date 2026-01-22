"""CallContext and related dataclasses for dynamic prompt customization.

This module defines the context structure passed at runtime to customize
agent prompts based on call type, property, payment, session, booking, etc.
"""

from dataclasses import dataclass, field


@dataclass
class PropertyInfo:
    """Property/hotel information for property-specific contexts.

    Minimal required fields:
    - property_name: Hotel name (e.g., "JW Marriott Miami")
    - hotel_id: Hotel ID for API calls (e.g., "123abc")
    """

    property_name: str = ""
    hotel_id: str = ""


@dataclass
class PaymentInfo:
    """Payment information for payment return contexts."""

    status: str = ""
    amount: float = 0.0
    currency: str = "USD"
    transaction_id: str | None = None
    timestamp: str | None = None


@dataclass
class SessionLeg:
    """Individual session leg information."""

    leg_type: str = ""
    # Add other leg fields as needed


@dataclass
class CallSessionContext:
    """Multi-leg call session context."""

    call_reference: str = ""
    session_legs: list[SessionLeg] = field(default_factory=list)
    previous_interactions: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Auto-convert nested dicts to typed objects."""
        # Convert session_legs dicts to SessionLeg objects
        if self.session_legs:
            self.session_legs = [
                SessionLeg(**leg) if isinstance(leg, dict) else leg
                for leg in self.session_legs
            ]


@dataclass
class DialMapBookingContext:
    """Booking context from dial map."""

    destination: str = ""
    check_in: str = ""
    check_out: str = ""
    rooms: int = 1
    adults: int = 2
    children: int = 0
    hotel_id: str | None = None  # Used for dated property URLs in live agent handoff


@dataclass
class AbandonedPaymentContext:
    """Abandoned payment recovery context."""

    timestamp: str = ""
    amount: float = 0.0
    currency: str = "USD"
    minutes_ago: int = 0
    reason: str | None = None


@dataclass
class CallContext:
    """Runtime context for dynamic prompt customization.

    This context is passed at runtime via runtime.context to customize the agent's
    system prompt based on call type, property, payment, session, etc.
    """

    type: str = (
        "general"  # property_specific, dated_property, payment_return, general
    )
    property: PropertyInfo | None = None
    payment: PaymentInfo | None = None
    session: CallSessionContext | None = None
    booking: DialMapBookingContext | None = None
    abandoned_payment: AbandonedPaymentContext | None = None
    user_phone: str | None = None
    thread_id: str | None = None
    call_reference: str | None = None
    dial_map_session_id: str | None = None

    def __post_init__(self) -> None:
        """Auto-convert nested dicts to typed objects if needed."""
        # Convert property dict to PropertyInfo
        if isinstance(self.property, dict):
            self.property = PropertyInfo(**self.property)

        # Convert payment dict to PaymentInfo
        if isinstance(self.payment, dict):
            self.payment = PaymentInfo(**self.payment)

        # Convert session dict to CallSessionContext
        if isinstance(self.session, dict):
            self.session = CallSessionContext(**self.session)

        # Convert booking dict to DialMapBookingContext
        if isinstance(self.booking, dict):
            self.booking = DialMapBookingContext(**self.booking)

        # Convert abandoned_payment dict to AbandonedPaymentContext
        if isinstance(self.abandoned_payment, dict):
            self.abandoned_payment = AbandonedPaymentContext(**self.abandoned_payment)
