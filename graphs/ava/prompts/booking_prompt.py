"""Booking context prompt for calls with pre-populated booking parameters."""
from datetime import datetime
from ava.context import DialMapBookingContext


def get_booking_context_prefix(booking: DialMapBookingContext) -> str:
    """
    Generate context prefix for booking-initiated calls.

    This handles cases where the user clicked through from a booking form
    and we have their search parameters already.

    Args:
        booking: The booking context with destination, dates, occupancy

    Returns:
        Context prefix to prepend to the main agent prompt
    """
    current_date = datetime.now().strftime("%Y-%m-%d")

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
    site_context = f" from {booking.site}" if booking.site else ""

    return f"""
**IMPORTANT BOOKING CONTEXT**: The customer has initiated a booking search{site_context} with the following preferences:

**Search Parameters**:
- Destination: {booking.destination or 'Not specified'}
- Check-in: {booking.check_in or 'Not specified'}
- Check-out: {booking.check_out or 'Not specified'}
- Rooms: {rooms_str}
- Guests: {occupancy_str}
{f'- Target Hotel ID: {booking.hotel_id}' if booking.hotel_id else ''}

**Current Date**: {current_date}

## YOUR APPROACH

### Initial Contact
- **Confirm their search**: Greet them warmly and acknowledge their booking search
- **Validate parameters**: Say something like "I see you're looking for {rooms_str} in {booking.destination or 'your destination'} from {booking.check_in or 'your check-in date'} to {booking.check_out or 'your check-out date'} for {occupancy_str}. Is that correct?"
- **Wait for confirmation** before proceeding with the search

### If Parameters Confirmed
- Use the provided booking parameters to search immediately
- Focus on {booking.destination or 'their destination'} for the dates specified
{f'- Prioritize hotel_id {booking.hotel_id} in your search' if booking.hotel_id else ''}

### If Parameters Need Adjustment
- Ask what they'd like to change (destination, dates, rooms, or occupancy)
- Update the relevant parameters and confirm before searching
- Maintain the other parameters unless they explicitly want to change them

### Search Execution
- When calling get_next_hotels, use the booking parameters:
  - location: "{booking.destination or 'their specified destination'}"
  - dates: {{"checkIn": "{booking.check_in}", "checkOut": "{booking.check_out}"}}
  - occupancy: {{"adults": {booking.adults or 2}, "children": {booking.children or 0}}}
  - rooms: {booking.rooms or 1}
{f'  - hotelId: "{booking.hotel_id}" (to search this specific hotel)' if booking.hotel_id else ''}

### Behavioral Guidelines
- **Don't ask questions you already have answers for** - you know their destination, dates, and occupancy
- **Do confirm** before searching to ensure accuracy
- **Be efficient** - they've already expressed intent by filling out a booking form
- **Build on their momentum** - they're ready to book, help them complete it quickly

### Voice Optimization
- Keep responses brief and natural (max 4 lines)
- No special characters or formatting symbols
- Use conversational language appropriate for phone calls
- Focus on moving the booking forward efficiently
"""
