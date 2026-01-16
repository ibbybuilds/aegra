"""Unit tests for url_generator module."""

import pytest
from ava_v1.context import CallContext, DialMapBookingContext, PropertyInfo
from ava_v1.shared_libraries.url_generator import (
    _build_location_url,
    _build_property_url,
    _extract_url_data,
    _find_hotel_context_in_stack,
    _format_dates_for_url,
    _validate_url_data,
    generate_reservation_url,
)


class TestDateFormatting:
    """Test date formatting functions."""

    def test_format_dates_valid(self):
        """Test formatting valid dates."""
        result = _format_dates_for_url("2026-01-04", "2026-01-06")
        assert result == "01/04/2026-01/06/2026"

    def test_format_dates_different_months(self):
        """Test formatting dates across different months."""
        result = _format_dates_for_url("2026-01-30", "2026-02-02")
        assert result == "01/30/2026-02/02/2026"

    def test_format_dates_invalid_format(self):
        """Test formatting with invalid date format."""
        result = _format_dates_for_url("01/04/2026", "01/06/2026")
        assert result is None

    def test_format_dates_malformed(self):
        """Test formatting with malformed dates."""
        result = _format_dates_for_url("2026-13-01", "2026-01-32")
        assert result is None


class TestPropertyURL:
    """Test property URL building."""

    def test_build_property_url_no_dates(self):
        """Test property URL without dates."""
        url = _build_property_url("39615853", None, None)
        assert url == "https://sandbox.reservationsportal.com/property/39615853"

    def test_build_property_url_with_dates(self):
        """Test property URL with dates and occupancy."""
        dates = ("2026-01-04", "2026-01-06")
        occupancy = {"numOfAdults": 2, "rooms": 1, "numOfChildren": 0}
        url = _build_property_url("39615853", dates, occupancy)
        assert "property/39615853" in url
        assert "dates=01/04/2026-01/06/2026" in url
        assert "numberAdults=2" in url
        assert "numberRooms=1" in url

    def test_build_property_url_multiple_rooms(self):
        """Test property URL with multiple rooms."""
        dates = ("2026-01-04", "2026-01-06")
        occupancy = {"numOfAdults": 4, "rooms": 2, "numOfChildren": 0}
        url = _build_property_url("39615853", dates, occupancy)
        assert "numberAdults=4" in url
        assert "numberRooms=2" in url


class TestLocationURL:
    """Test location search URL building."""

    def test_build_location_url(self):
        """Test location URL with all parameters."""
        geo_data = {
            "latitude": 25.7617,
            "longitude": -80.1918,
            "formattedAddress": "Miami, Florida, USA",
            "countryCode": "US",
        }
        dates = ("2026-01-04", "2026-01-06")
        occupancy = {"numOfAdults": 2, "rooms": 1, "numOfChildren": 0}

        url = _build_location_url(geo_data, dates, occupancy)
        assert "availability" in url
        assert "latitude=25.7617" in url
        assert "longitude=-80.1918" in url
        assert "locality=Miami" in url
        assert "region=Florida" in url
        assert "country=USA" in url
        assert "dates=01/04/2026-01/06/2026" in url
        assert "numberAdults=2" in url
        assert "numberRooms=1" in url
        assert "numberChildren=0" in url

    def test_build_location_url_with_children(self):
        """Test location URL with children."""
        geo_data = {
            "latitude": 25.7617,
            "longitude": -80.1918,
            "formattedAddress": "Miami, FL, USA",
            "countryCode": "US",
        }
        dates = ("2026-01-04", "2026-01-06")
        occupancy = {"numOfAdults": 2, "rooms": 1, "numOfChildren": 2}

        url = _build_location_url(geo_data, dates, occupancy)
        assert "numberChildren=2" in url

    def test_build_location_url_special_characters(self):
        """Test location URL with special characters in name."""
        geo_data = {
            "latitude": 28.5383,
            "longitude": -81.3792,
            "formattedAddress": "Orlando (Lake Buena Vista), Florida, USA",
            "countryCode": "US",
        }
        dates = ("2026-01-04", "2026-01-06")
        occupancy = {"numOfAdults": 2, "rooms": 1, "numOfChildren": 0}

        url = _build_location_url(geo_data, dates, occupancy)
        # Should be URL encoded
        assert "locality=Orlando" in url
        assert "Lake" in url


class TestFindHotelContext:
    """Test finding hotel context in stack."""

    def test_find_hotel_context_in_stack(self):
        """Test finding RoomList context with hotel_id."""
        context_stack = [
            {"type": "HotelList", "search_key": "Miami"},
            {"type": "RoomList", "search_key": "Miami", "hotel_id": "39615853"},
            {"type": "BookingPending", "booking_hash": "abc123"},
        ]

        result = _find_hotel_context_in_stack(context_stack)
        assert result is not None
        assert result["type"] == "RoomList"
        assert result["hotel_id"] == "39615853"

    def test_find_hotel_context_not_found(self):
        """Test when no RoomList context exists."""
        context_stack = [
            {"type": "HotelList", "search_key": "Miami"},
            {"type": "BookingPending", "booking_hash": "abc123"},
        ]

        result = _find_hotel_context_in_stack(context_stack)
        assert result is None

    def test_find_hotel_context_empty_stack(self):
        """Test with empty context stack."""
        result = _find_hotel_context_in_stack([])
        assert result is None


class TestExtractURLData:
    """Test URL data extraction."""

    def test_extract_hotel_list(self):
        """Test extracting data from HotelList context."""
        context_stack = [{"type": "HotelList", "search_key": "Miami"}]
        active_searches = {
            "Miami": {
                "checkIn": "2026-01-04",
                "checkOut": "2026-01-06",
                "occupancy": {"numOfAdults": 2, "rooms": 1},
                "geoHash": "abc123def456",
            }
        }

        url_data = _extract_url_data(context_stack, active_searches, None)
        assert url_data is not None
        assert url_data["url_type"] == "location"
        assert url_data["search_key"] == "Miami"
        assert url_data["dates"] == ("2026-01-04", "2026-01-06")

    def test_extract_room_list_with_dates(self):
        """Test extracting data from RoomList context with dates."""
        context_stack = [
            {"type": "RoomList", "search_key": "Miami", "hotel_id": "39615853"}
        ]
        active_searches = {
            "Miami": {
                "checkIn": "2026-01-04",
                "checkOut": "2026-01-06",
                "occupancy": {"numOfAdults": 2, "rooms": 1},
            }
        }

        url_data = _extract_url_data(context_stack, active_searches, None)
        assert url_data is not None
        assert url_data["url_type"] == "dated_property"
        assert url_data["hotel_id"] == "39615853"
        assert url_data["dates"] == ("2026-01-04", "2026-01-06")

    def test_extract_room_list_without_dates(self):
        """Test extracting data from RoomList without dates in active_searches."""
        context_stack = [
            {"type": "RoomList", "search_key": "Miami", "hotel_id": "39615853"}
        ]
        active_searches = {}

        url_data = _extract_url_data(context_stack, active_searches, None)
        assert url_data is not None
        assert url_data["url_type"] == "property"
        assert url_data["hotel_id"] == "39615853"

    def test_extract_hotel_details(self):
        """Test extracting data from HotelDetails context."""
        context_stack = [{"type": "HotelDetails", "hotel_id": "39615853"}]
        active_searches = {}

        url_data = _extract_url_data(context_stack, active_searches, None)
        assert url_data is not None
        assert url_data["url_type"] == "property"
        assert url_data["hotel_id"] == "39615853"

    def test_extract_booking_pending_with_stack_walkback(self):
        """Test extracting data from BookingPending with stack walk-back."""
        context_stack = [
            {"type": "HotelList", "search_key": "Miami"},
            {"type": "RoomList", "search_key": "Miami", "hotel_id": "39615853"},
            {"type": "BookingPending", "booking_hash": "abc123"},
        ]
        active_searches = {
            "Miami": {
                "checkIn": "2026-01-04",
                "checkOut": "2026-01-06",
                "occupancy": {"numOfAdults": 2, "rooms": 1},
            }
        }

        url_data = _extract_url_data(context_stack, active_searches, None)
        assert url_data is not None
        assert url_data["url_type"] == "dated_property"
        assert url_data["hotel_id"] == "39615853"

    def test_extract_empty_stack_with_property_context(self):
        """Test fallback to CallContext.property when stack is empty."""
        context_stack = []
        active_searches = {}
        call_context = CallContext(
            type="property_specific",
            property=PropertyInfo(hotel_id="39615853", property_name="Test Hotel"),
        )

        url_data = _extract_url_data(context_stack, active_searches, call_context)
        assert url_data is not None
        assert url_data["url_type"] == "property"
        assert url_data["hotel_id"] == "39615853"

    def test_extract_empty_stack_with_booking_context_property(self):
        """Test fallback to CallContext.booking with hotel_id."""
        context_stack = []
        active_searches = {}
        call_context = CallContext(
            type="booking",
            booking=DialMapBookingContext(
                destination="Miami",
                check_in="2026-01-04",
                check_out="2026-01-06",
                hotel_id="39615853",
                adults=2,
                rooms=1,
                children=0,
            ),
        )

        url_data = _extract_url_data(context_stack, active_searches, call_context)
        assert url_data is not None
        assert url_data["url_type"] == "dated_property"
        assert url_data["hotel_id"] == "39615853"
        assert url_data["dates"] == ("2026-01-04", "2026-01-06")

    def test_extract_empty_stack_with_booking_context_location(self):
        """Test fallback to CallContext.booking with destination only."""
        context_stack = []
        active_searches = {}
        call_context = CallContext(
            type="booking",
            booking=DialMapBookingContext(
                destination="Miami",
                check_in="2026-01-04",
                check_out="2026-01-06",
                adults=2,
                rooms=1,
                children=0,
            ),
        )

        url_data = _extract_url_data(context_stack, active_searches, call_context)
        assert url_data is not None
        assert url_data["url_type"] == "location_from_booking"
        assert url_data["destination"] == "Miami"
        assert url_data["dates"] == ("2026-01-04", "2026-01-06")

    def test_extract_empty_stack_no_context(self):
        """Test with empty stack and no CallContext."""
        url_data = _extract_url_data([], {}, None)
        assert url_data is None


class TestValidateURLData:
    """Test URL data validation."""

    def test_validate_dated_property_valid(self):
        """Test validating complete dated property data."""
        url_data = {
            "url_type": "dated_property",
            "hotel_id": "123",
            "dates": ("2026-01-04", "2026-01-06"),
            "occupancy": {"numOfAdults": 2},
        }
        assert _validate_url_data(url_data) is True

    def test_validate_dated_property_missing_hotel_id(self):
        """Test validating dated property without hotel_id."""
        url_data = {
            "url_type": "dated_property",
            "dates": ("2026-01-04", "2026-01-06"),
            "occupancy": {"numOfAdults": 2},
        }
        assert _validate_url_data(url_data) is False

    def test_validate_property_valid(self):
        """Test validating property data."""
        url_data = {"url_type": "property", "hotel_id": "123"}
        assert _validate_url_data(url_data) is True

    def test_validate_property_missing_hotel_id(self):
        """Test validating property without hotel_id."""
        url_data = {"url_type": "property"}
        assert _validate_url_data(url_data) is False

    def test_validate_location_valid(self):
        """Test validating complete location data."""
        url_data = {
            "url_type": "location",
            "search_key": "Miami",
            "dates": ("2026-01-04", "2026-01-06"),
            "occupancy": {"numOfAdults": 2},
        }
        assert _validate_url_data(url_data) is True

    def test_validate_location_missing_dates(self):
        """Test validating location without dates."""
        url_data = {
            "url_type": "location",
            "search_key": "Miami",
            "occupancy": {"numOfAdults": 2},
        }
        assert _validate_url_data(url_data) is False


class TestGenerateReservationURL:
    """Test main URL generation function."""

    @pytest.mark.asyncio
    async def test_generate_url_property_only(self):
        """Test generating property URL without dates."""
        context_stack = [{"type": "HotelDetails", "hotel_id": "39615853"}]
        active_searches = {}

        url = await generate_reservation_url(context_stack, active_searches)
        assert url is not None
        assert "property/39615853" in url
        assert "dates=" not in url

    @pytest.mark.asyncio
    async def test_generate_url_empty_stack(self):
        """Test generating URL with empty stack."""
        url = await generate_reservation_url([], {})
        assert url is None

    @pytest.mark.asyncio
    async def test_generate_url_from_call_context(self):
        """Test generating URL from CallContext fallback."""
        context_stack = []
        active_searches = {}
        call_context = CallContext(
            type="property_specific",
            property=PropertyInfo(hotel_id="39615853", property_name="Test Hotel"),
        )

        url = await generate_reservation_url(
            context_stack, active_searches, call_context
        )
        assert url is not None
        assert "property/39615853" in url

    @pytest.mark.asyncio
    async def test_generate_url_invalid_dates(self):
        """Test that invalid dates result in property URL without query params."""
        context_stack = [
            {"type": "RoomList", "search_key": "Miami", "hotel_id": "39615853"}
        ]
        active_searches = {
            "Miami": {
                "checkIn": "invalid-date",
                "checkOut": "2026-01-06",
                "occupancy": {"numOfAdults": 2, "rooms": 1},
            }
        }

        url = await generate_reservation_url(context_stack, active_searches)
        # Should fall back to property URL without dates
        assert url is not None
        assert "property/39615853" in url
