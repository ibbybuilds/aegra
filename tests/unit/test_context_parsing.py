"""Tests for context parsing and prompt customization."""
import pytest
import sys
from pathlib import Path

# Add graphs to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "graphs"))

from ava.context import (
    CallContext,
    PropertyInfo,
    PaymentInfo,
    CallSessionContext,
    CallSessionLeg,
    DialMapBookingContext,
    AbandonedPaymentContext
)
from src.agent_server.utils.context_parser import parse_ava_context
from ava.dynamic_prompt import get_customized_prompt


class TestContextParsing:
    """Test context parsing from API requests."""

    def test_parse_general_context(self):
        """Test parsing general context (empty/null)."""
        context = parse_ava_context(None)
        assert context.type == "general"
        assert context.property is None
        assert context.payment is None
        assert context.booking is None

    def test_parse_property_specific_context(self):
        """Test parsing property-specific context."""
        context_dict = {
            "call_context": {
                "type": "property_specific",
                "property": {
                    "property_id": "prop_123",
                    "property_name": "Grand Hotel",
                    "hotel_id": "hotel_456",
                    "location": "Las Vegas, NV",
                    "features": ["pool", "spa"]
                }
            }
        }
        context = parse_ava_context(context_dict)
        assert context.type == "property_specific"
        assert context.property is not None
        assert context.property.property_name == "Grand Hotel"
        assert context.property.hotel_id == "hotel_456"
        assert "pool" in context.property.features

    def test_parse_booking_context(self):
        """Test parsing booking context."""
        context_dict = {
            "call_context": {
                "type": "general",
                "booking": {
                    "destination": "Las Vegas",
                    "check_in": "2024-03-15",
                    "check_out": "2024-03-18",
                    "rooms": 2,
                    "adults": 4,
                    "children": 0
                }
            }
        }
        context = parse_ava_context(context_dict)
        assert context.booking is not None
        assert context.booking.destination == "Las Vegas"
        assert context.booking.rooms == 2
        assert context.booking.adults == 4

    def test_parse_property_with_booking(self):
        """Test parsing property + booking hybrid context."""
        context_dict = {
            "call_context": {
                "type": "property_specific",
                "property": {
                    "property_id": "prop_123",
                    "property_name": "Grand Hotel",
                    "hotel_id": "hotel_456",
                    "location": "Las Vegas, NV"
                },
                "booking": {
                    "destination": "Las Vegas",
                    "check_in": "2024-03-15",
                    "check_out": "2024-03-18",
                    "rooms": 1,
                    "adults": 2
                },
                "dial_map_session_id": "session_789"
            }
        }
        context = parse_ava_context(context_dict)
        assert context.property is not None
        assert context.booking is not None
        assert context.property.property_name == "Grand Hotel"
        assert context.booking.destination == "Las Vegas"
        assert context.dial_map_session_id == "session_789"

    def test_parse_abandoned_payment_context(self):
        """Test parsing abandoned payment context."""
        context_dict = {
            "call_context": {
                "type": "thread_continuation",
                "thread_id": "thread_abc123",
                "abandoned_payment": {
                    "timestamp": "2024-03-10T10:25:00Z",
                    "amount": 150.00,
                    "currency": "USD",
                    "minutes_ago": 5,
                    "reason": "dropped"
                }
            }
        }
        context = parse_ava_context(context_dict)
        assert context.abandoned_payment is not None
        assert context.abandoned_payment.amount == 150.00
        assert context.abandoned_payment.minutes_ago == 5
        assert context.abandoned_payment.reason == "dropped"
        assert context.thread_id == "thread_abc123"

    def test_parse_payment_return_context(self):
        """Test parsing payment return context."""
        context_dict = {
            "call_context": {
                "type": "payment_return",
                "payment": {
                    "status": "completed",
                    "amount": 299.99,
                    "currency": "USD",
                    "transaction_id": "txn_789",
                    "timestamp": "2024-03-10T10:30:00Z"
                }
            }
        }
        context = parse_ava_context(context_dict)
        assert context.type == "payment_return"
        assert context.payment is not None
        assert context.payment.status == "completed"
        assert context.payment.transaction_id == "txn_789"

    def test_parse_session_context(self):
        """Test parsing session context with call legs."""
        context_dict = {
            "call_context": {
                "type": "general",
                "session": {
                    "call_reference": "CR123456",
                    "session_legs": [
                        {
                            "leg_id": "leg1",
                            "call_sid": "sid1",
                            "leg_type": "initial",
                            "timestamp": "2024-03-10T10:00:00Z"
                        },
                        {
                            "leg_id": "leg2",
                            "call_sid": "sid2",
                            "leg_type": "payment",
                            "timestamp": "2024-03-10T10:05:00Z"
                        }
                    ],
                    "previous_interactions": ["Asked about rooms", "Selected room 101"]
                }
            }
        }
        context = parse_ava_context(context_dict)
        assert context.session is not None
        assert context.session.call_reference == "CR123456"
        assert len(context.session.session_legs) == 2
        assert context.session.session_legs[0].leg_type == "initial"
        assert len(context.session.previous_interactions) == 2


class TestPromptCustomization:
    """Test prompt customization based on context."""

    def test_general_prompt(self):
        """Test general context returns base prompt."""
        context = CallContext(type="general")
        prompt = get_customized_prompt(context)
        assert "HOTEL SEARCH AGENT SYSTEM PROMPT" in prompt
        assert "property_specific" not in prompt.lower() or "property-specific" not in prompt.lower()

    def test_property_specific_prompt(self):
        """Test property-specific context returns customized prompt."""
        property_info = PropertyInfo(
            property_id="prop_123",
            property_name="Grand Hotel",
            hotel_id="hotel_456",
            location="Las Vegas, NV"
        )
        context = CallContext(type="property_specific", property=property_info)
        prompt = get_customized_prompt(context)
        assert "Grand Hotel" in prompt
        assert "hotel_456" in prompt
        assert "PROPERTY-SPECIFIC" in prompt

    def test_booking_only_prompt(self):
        """Test booking context adds booking prefix."""
        booking = DialMapBookingContext(
            destination="Las Vegas",
            check_in="2024-03-15",
            check_out="2024-03-18",
            rooms=1,
            adults=2
        )
        context = CallContext(type="general", booking=booking)
        prompt = get_customized_prompt(context)
        assert "BOOKING CONTEXT" in prompt
        assert "Las Vegas" in prompt
        assert "2024-03-15" in prompt

    def test_property_booking_hybrid_prompt(self):
        """Test property + booking hybrid uses property-booking prompt."""
        property_info = PropertyInfo(
            property_id="prop_123",
            property_name="Grand Hotel",
            hotel_id="hotel_456",
            location="Las Vegas, NV"
        )
        booking = DialMapBookingContext(
            destination="Las Vegas",
            check_in="2024-03-15",
            check_out="2024-03-18",
            rooms=1,
            adults=2
        )
        context = CallContext(
            type="property_specific",
            property=property_info,
            booking=booking
        )
        prompt = get_customized_prompt(context)
        # Should contain both property and booking information
        assert "Grand Hotel" in prompt
        assert "hotel_456" in prompt
        assert "2024-03-15" in prompt
        assert "BOOKING CONTEXT" in prompt

    def test_abandoned_payment_prompt_priority(self):
        """Test abandoned payment gets highest priority."""
        abandoned = AbandonedPaymentContext(
            timestamp="2024-03-10T10:25:00Z",
            amount=150.00,
            currency="USD",
            minutes_ago=5,
            reason="dropped"
        )
        context = CallContext(
            type="thread_continuation",
            thread_id="thread_123",
            abandoned_payment=abandoned
        )
        prompt = get_customized_prompt(context)
        assert "ABANDONED PAYMENT RECOVERY" in prompt
        assert "150.00" in prompt
        assert "dropped" in prompt

    def test_payment_return_prompt(self):
        """Test payment return context."""
        payment = PaymentInfo(
            status="completed",
            amount=299.99,
            currency="USD",
            transaction_id="txn_789"
        )
        context = CallContext(type="payment_return", payment=payment)
        prompt = get_customized_prompt(context)
        assert "payment processing" in prompt.lower()
        assert "299.99" in prompt
        assert "txn_789" in prompt

    def test_thread_continuation_prompt(self):
        """Test thread continuation context."""
        context = CallContext(
            type="thread_continuation",
            thread_id="thread_abc123"
        )
        prompt = get_customized_prompt(context)
        assert "returning customer" in prompt.lower()
        assert "thread_abc123" in prompt


class TestContextDataclasses:
    """Test context dataclass construction and __post_init__."""

    def test_call_context_post_init_converts_dicts(self):
        """Test __post_init__ converts dict to typed objects."""
        context = CallContext(
            type="property_specific",
            property={
                "property_id": "prop_123",
                "property_name": "Grand Hotel",
                "hotel_id": "hotel_456"
            },
            booking={
                "destination": "Las Vegas",
                "check_in": "2024-03-15",
                "check_out": "2024-03-18"
            }
        )
        assert isinstance(context.property, PropertyInfo)
        assert isinstance(context.booking, DialMapBookingContext)
        assert context.property.property_name == "Grand Hotel"
        assert context.booking.destination == "Las Vegas"

    def test_session_context_with_legs(self):
        """Test session context converts leg dicts."""
        context = CallContext(
            type="general",
            session={
                "call_reference": "CR123",
                "session_legs": [
                    {
                        "leg_id": "leg1",
                        "call_sid": "sid1",
                        "leg_type": "initial",
                        "timestamp": "2024-03-10T10:00:00Z"
                    }
                ]
            }
        )
        assert isinstance(context.session, CallSessionContext)
        assert len(context.session.session_legs) == 1
        assert isinstance(context.session.session_legs[0], CallSessionLeg)
        assert context.session.session_legs[0].leg_type == "initial"
