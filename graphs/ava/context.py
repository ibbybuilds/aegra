"""Context schema for AVA agent runtime configuration."""
from dataclasses import dataclass, field
from typing import Optional, Literal


@dataclass
class PropertyInfo:
    """Information about a specific property."""
    property_id: str
    property_name: str
    hotel_id: str
    location: Optional[str] = None
    features: list[str] = field(default_factory=list)


@dataclass
class PaymentInfo:
    """Information about payment status."""
    status: Optional[Literal['completed', 'failed', 'pending']] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class CallSessionLeg:
    """Information about a single leg in a multi-leg call session."""
    leg_id: str
    call_sid: str
    leg_type: Literal['initial', 'payment', 'return', 'transfer']
    timestamp: str


@dataclass
class CallSessionContext:
    """Call session context for multi-leg calls."""
    call_reference: str
    session_legs: list[CallSessionLeg] = field(default_factory=list)
    previous_interactions: list[str] = field(default_factory=list)


@dataclass
class DialMapBookingContext:
    """
    Booking context extracted from dial-map session.
    This is the transformed format passed to the agent.
    """
    destination: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    rooms: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    hotel_id: Optional[str] = None
    site: Optional[str] = None


@dataclass
class AbandonedPaymentContext:
    """Information about an abandoned payment."""
    timestamp: str
    amount: float
    currency: str
    minutes_ago: int
    reason: Literal['timeout', 'dropped', 'unknown']


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
    session: Optional[CallSessionContext] = None
    booking: Optional[DialMapBookingContext] = None
    abandoned_payment: Optional[AbandonedPaymentContext] = None
    user_phone: Optional[str] = None
    thread_id: Optional[str] = None
    call_reference: Optional[str] = None
    dial_map_session_id: Optional[str] = None

    def __post_init__(self):
        """Convert dict to typed objects if needed."""
        if isinstance(self.property, dict):
            self.property = PropertyInfo(**self.property)
        if isinstance(self.payment, dict):
            self.payment = PaymentInfo(**self.payment)
        if isinstance(self.session, dict):
            # Convert session_legs dicts to CallSessionLeg objects
            session_legs = []
            for leg in self.session.get('session_legs', []):
                if isinstance(leg, dict):
                    session_legs.append(CallSessionLeg(**leg))
                else:
                    session_legs.append(leg)
            self.session = CallSessionContext(
                call_reference=self.session.get('call_reference', ''),
                session_legs=session_legs,
                previous_interactions=self.session.get('previous_interactions', [])
            )
        if isinstance(self.booking, dict):
            self.booking = DialMapBookingContext(**self.booking)
        if isinstance(self.abandoned_payment, dict):
            self.abandoned_payment = AbandonedPaymentContext(**self.abandoned_payment)
