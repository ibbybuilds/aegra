"""Unit tests for SSE utilities"""

from aegra_api.utils.sse_utils import extract_event_sequence, generate_event_id


class TestGenerateEventId:
    """Test generate_event_id function"""

    def test_generate_event_id_basic(self):
        """Test basic event ID generation"""
        result = generate_event_id("run-123", 1)
        assert result == "run-123_event_1"

    def test_generate_event_id_zero_sequence(self):
        """Test event ID generation with zero sequence"""
        result = generate_event_id("run-456", 0)
        assert result == "run-456_event_0"

    def test_generate_event_id_large_sequence(self):
        """Test event ID generation with large sequence number"""
        result = generate_event_id("run-789", 999999)
        assert result == "run-789_event_999999"

    def test_generate_event_id_with_special_chars(self):
        """Test event ID generation with special characters in run_id"""
        result = generate_event_id("run_123-abc", 5)
        assert result == "run_123-abc_event_5"

    def test_generate_event_id_empty_run_id(self):
        """Test event ID generation with empty run_id"""
        result = generate_event_id("", 1)
        assert result == "_event_1"


class TestExtractEventSequence:
    """Test extract_event_sequence function"""

    def test_extract_event_sequence_basic(self):
        """Test basic sequence extraction"""
        result = extract_event_sequence("run-123_event_1")
        assert result == 1

    def test_extract_event_sequence_zero(self):
        """Test sequence extraction with zero"""
        result = extract_event_sequence("run-456_event_0")
        assert result == 0

    def test_extract_event_sequence_large(self):
        """Test sequence extraction with large number"""
        result = extract_event_sequence("run-789_event_999999")
        assert result == 999999

    def test_extract_event_sequence_with_special_chars(self):
        """Test sequence extraction with special characters in run_id"""
        result = extract_event_sequence("run_123-abc_event_5")
        assert result == 5

    def test_extract_event_sequence_multiple_underscores(self):
        """Test sequence extraction with multiple underscores"""
        result = extract_event_sequence("run_with_underscores_event_42")
        assert result == 42

    def test_extract_event_sequence_invalid_format(self):
        """Test sequence extraction with invalid format"""
        result = extract_event_sequence("invalid_format")
        assert result == 0

    def test_extract_event_sequence_no_event_prefix(self):
        """Test sequence extraction without _event_ prefix"""
        result = extract_event_sequence("run-123_42")
        assert result == 0

    def test_extract_event_sequence_empty_string(self):
        """Test sequence extraction with empty string"""
        result = extract_event_sequence("")
        assert result == 0

    def test_extract_event_sequence_non_numeric(self):
        """Test sequence extraction with non-numeric sequence"""
        result = extract_event_sequence("run-123_event_abc")
        assert result == 0

    def test_extract_event_sequence_negative_number(self):
        """Test sequence extraction with negative number"""
        result = extract_event_sequence("run-123_event_-1")
        assert result == -1

    def test_extract_event_sequence_float(self):
        """Test sequence extraction with float-like string"""
        result = extract_event_sequence("run-123_event_1.5")
        assert result == 0  # int() conversion fails for float strings


class TestEventIdRoundTrip:
    """Test round-trip functionality between generate and extract"""

    def test_round_trip_basic(self):
        """Test round-trip with basic values"""
        run_id = "run-123"
        sequence = 42

        event_id = generate_event_id(run_id, sequence)
        extracted_sequence = extract_event_sequence(event_id)

        assert extracted_sequence == sequence

    def test_round_trip_zero(self):
        """Test round-trip with zero sequence"""
        run_id = "run-456"
        sequence = 0

        event_id = generate_event_id(run_id, sequence)
        extracted_sequence = extract_event_sequence(event_id)

        assert extracted_sequence == sequence

    def test_round_trip_large(self):
        """Test round-trip with large sequence"""
        run_id = "run-789"
        sequence = 999999

        event_id = generate_event_id(run_id, sequence)
        extracted_sequence = extract_event_sequence(event_id)

        assert extracted_sequence == sequence

    def test_round_trip_special_chars(self):
        """Test round-trip with special characters"""
        run_id = "run_123-abc_def"
        sequence = 100

        event_id = generate_event_id(run_id, sequence)
        extracted_sequence = extract_event_sequence(event_id)

        assert extracted_sequence == sequence
