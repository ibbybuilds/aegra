"""Property-specific prompt with booking context injection."""
from datetime import datetime
from ava.context import PropertyInfo, DialMapBookingContext
from ava.prompts.property_specific_prompt import get_property_specific_prompt


def get_property_booking_prompt(property_data: PropertyInfo, booking: DialMapBookingContext) -> str:
    """
    Generate a hybrid prompt for property-specific calls with pre-populated booking data.

    This combines the property-specific behavior (focusing on one hotel) with
    booking context (pre-filled search parameters).

    Args:
        property_data: PropertyInfo object containing hotel details
        booking: DialMapBookingContext with search parameters

    Returns:
        Complete system prompt combining property focus and booking data
    """
    # Start with the base property-specific prompt
    base_prompt = get_property_specific_prompt(property_data)

    # Build occupancy string
    occupancy_parts = []
    if booking.adults:
        occupancy_parts.append(f"{booking.adults} adult{'s' if booking.adults > 1 else ''}")
    if booking.children:
        occupancy_parts.append(f"{booking.children} child{'ren' if booking.children > 1 else ''}")
    occupancy_str = " and ".join(occupancy_parts) if occupancy_parts else "guests"

    # Build rooms string
    rooms_str = f"{booking.rooms} room{'s' if booking.rooms and booking.rooms > 1 else ''}" if booking.rooms else "a room"

    # Build site reference if available
    site_context = f" through {booking.site}" if booking.site else ""

    current_date = datetime.now().strftime("%Y-%m-%d")

    # Create the booking context injection that will be inserted into the base prompt
    booking_injection = f"""

## BOOKING CONTEXT - PRE-POPULATED SEARCH

**IMPORTANT**: The customer has already expressed interest in {property_data.property_name}{site_context} and provided their booking preferences:

**Pre-Filled Search Parameters**:
- Destination: {booking.destination or property_data.location}
- Check-in: {booking.check_in or 'Not specified'}
- Check-out: {booking.check_out or 'Not specified'}
- Rooms: {rooms_str}
- Guests: {occupancy_str}
- Target Property: {property_data.property_name} (hotel_id: {property_data.hotel_id})

**Current Date**: {current_date}

### MODIFIED WORKFLOW FOR BOOKING CONTEXT

Since you already have their search parameters, your workflow is streamlined:

1. **Greet & Confirm**: Welcome them to {property_data.property_name} and acknowledge their booking search
   - Example: "Welcome to {property_data.property_name}! I see you're looking for {rooms_str} from {booking.check_in or 'your check-in date'} to {booking.check_out or 'your check-out date'} for {occupancy_str}. Let me check our availability for you."

2. **Confirm Before Searching**:
   - Quickly validate: "Just to confirm - {rooms_str} from {booking.check_in} to {booking.check_out} for {occupancy_str}, is that correct?"
   - Wait for their confirmation (Yes/No)

3. **Search Immediately After Confirmation**:
   - Use the pre-filled parameters for your search
   - Call get_next_hotels with:
     - location: "{booking.destination or property_data.location}"
     - hotelId: "{property_data.hotel_id}"
     - dates: {{"checkIn": "{booking.check_in}", "checkOut": "{booking.check_out}"}}
     - occupancy: {{"adults": {booking.adults or 2}, "children": {booking.children or 0}}}
     - rooms: {booking.rooms or 1}

4. **Handle Adjustments**: If they want to modify any parameters:
   - Ask what they'd like to change
   - Update only the changed parameters
   - Keep the rest of the booking data intact
   - Confirm the new parameters before searching

### BEHAVIORAL MODIFICATIONS

**What NOT to ask** (you already have this information):
- ❌ "Where would you like to stay?" (they came to {property_data.property_name})
- ❌ "What dates are you looking for?" (you have {booking.check_in} to {booking.check_out})
- ❌ "How many guests?" (you have {occupancy_str})
- ❌ "How many rooms?" (you have {rooms_str})

**What TO do**:
- ✅ Confirm their parameters quickly in one go
- ✅ Search immediately after confirmation
- ✅ Show results and help them book efficiently
- ✅ Build on their booking momentum - they're ready to book

**Efficiency Focus**:
- They've already filled out a booking form - respect their time
- Minimize redundant questions
- Fast-track to showing availability
- One confirmation, then search, then results

### Voice Optimization
- Keep initial greeting + confirmation under 4 lines
- Use natural phone conversation style
- No special characters or formatting symbols
- Focus on speed and efficiency

---

## CONTINUE WITH STANDARD PROPERTY-SPECIFIC GUIDELINES BELOW
"""

    # Insert the booking context after the PROPERTY-SPECIFIC BEHAVIOR section
    # Find where to inject it
    split_point = base_prompt.find("## PERSONALITY & COMMUNICATION")

    if split_point != -1:
        # Insert booking context before PERSONALITY & COMMUNICATION
        modified_prompt = base_prompt[:split_point] + booking_injection + base_prompt[split_point:]
    else:
        # Fallback: append to the end if structure changed
        modified_prompt = base_prompt + booking_injection

    return modified_prompt
