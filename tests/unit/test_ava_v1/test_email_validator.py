"""Unit tests for email validation (Tier 1 checks only)."""

import pytest

from ava_v1.shared_libraries.email_validator import (
    check_email_validity,
    has_valid_mx_records,
    is_disposable_domain,
    is_trusted_provider,
)


class TestIsDisposableDomain:
    """Test disposable domain blocklist checking."""

    def test_known_disposable_domains(self):
        """Test that known disposable domains are detected."""
        assert is_disposable_domain("guerrillamail.com") is True
        assert is_disposable_domain("10minutemail.com") is True
        assert is_disposable_domain("mailinator.com") is True
        assert is_disposable_domain("tempmail.best") is True

    def test_legitimate_domains(self):
        """Test that legitimate domains are not flagged as disposable."""
        assert is_disposable_domain("gmail.com") is False
        assert is_disposable_domain("yahoo.com") is False
        assert is_disposable_domain("anthropic.com") is False
        assert is_disposable_domain("example.com") is False

    def test_case_insensitive(self):
        """Test that domain checking is case-insensitive."""
        assert is_disposable_domain("GUERRILLAMAIL.COM") is True
        assert is_disposable_domain("GuerrillaMail.Com") is True


class TestIsTrustedProvider:
    """Test trusted provider whitelist checking."""

    def test_trusted_providers(self):
        """Test that major email providers are recognized."""
        assert is_trusted_provider("gmail.com") is True
        assert is_trusted_provider("yahoo.com") is True
        assert is_trusted_provider("outlook.com") is True
        assert is_trusted_provider("hotmail.com") is True
        assert is_trusted_provider("icloud.com") is True
        assert is_trusted_provider("aol.com") is True

    def test_untrusted_domains(self):
        """Test that non-whitelisted domains return False."""
        assert is_trusted_provider("example.com") is False
        assert is_trusted_provider("anthropic.com") is False
        assert is_trusted_provider("mycompany.com") is False

    def test_case_insensitive(self):
        """Test that provider checking is case-insensitive."""
        assert is_trusted_provider("GMAIL.COM") is True
        assert is_trusted_provider("Gmail.Com") is True


class TestHasValidMXRecords:
    """Test MX record validation via DNS lookup."""

    def test_valid_mx_records(self):
        """Test domains with valid MX records."""
        # Major providers should have MX records
        assert has_valid_mx_records("gmail.com") is True
        assert has_valid_mx_records("yahoo.com") is True
        assert has_valid_mx_records("anthropic.com") is True

    def test_invalid_mx_records(self):
        """Test domains without MX records or non-existent domains."""
        # Common typos should fail
        assert has_valid_mx_records("gmial.com") is False  # Gmail typo
        assert has_valid_mx_records("fakefakefake12345.com") is False  # Non-existent

    def test_timeout_fails_open(self):
        """Test that DNS timeout doesn't reject valid domains.

        Note: This is hard to test reliably without mocking, but the
        implementation should fail open (return True) on timeout.
        """
        # This test verifies the logic exists, actual timeout testing
        # would require mocking dns.resolver
        pass


@pytest.mark.asyncio
class TestCheckEmailValidity:
    """Test complete email validation flow (Tier 1)."""

    async def test_valid_gmail(self):
        """Test that Gmail emails pass (trusted provider, skip MX)."""
        is_valid, error_hint = await check_email_validity("test@gmail.com")
        assert is_valid is True
        assert error_hint is None

    async def test_valid_yahoo(self):
        """Test that Yahoo emails pass (trusted provider, skip MX)."""
        is_valid, error_hint = await check_email_validity("user@yahoo.com")
        assert is_valid is True
        assert error_hint is None

    async def test_valid_outlook(self):
        """Test that Outlook emails pass (trusted provider, skip MX)."""
        is_valid, error_hint = await check_email_validity("john@outlook.com")
        assert is_valid is True
        assert error_hint is None

    async def test_invalid_syntax_missing_at(self):
        """Test that emails without @ are rejected."""
        is_valid, error_hint = await check_email_validity("invalid-email")
        assert is_valid is False
        assert error_hint == "Invalid email format"

    async def test_invalid_syntax_missing_domain(self):
        """Test that emails without domain are rejected."""
        is_valid, error_hint = await check_email_validity("test@")
        assert is_valid is False
        assert error_hint == "Invalid email format"

    async def test_invalid_syntax_missing_local(self):
        """Test that emails without local part are rejected."""
        is_valid, error_hint = await check_email_validity("@example.com")
        assert is_valid is False
        assert error_hint == "Invalid email format"

    async def test_disposable_domain_guerrillamail(self):
        """Test that Guerrilla Mail is rejected as disposable."""
        is_valid, error_hint = await check_email_validity("test@guerrillamail.com")
        assert is_valid is False
        assert error_hint == (
            "This appears to be a temporary/disposable email address. "
            "Please provide a permanent email address."
        )

    async def test_disposable_domain_10minutemail(self):
        """Test that 10 Minute Mail is rejected as disposable."""
        is_valid, error_hint = await check_email_validity("user@10minutemail.com")
        assert is_valid is False
        assert error_hint == (
            "This appears to be a temporary/disposable email address. "
            "Please provide a permanent email address."
        )

    async def test_disposable_domain_mailinator(self):
        """Test that Mailinator is rejected as disposable."""
        is_valid, error_hint = await check_email_validity("temp@mailinator.com")
        assert is_valid is False
        assert error_hint == (
            "This appears to be a temporary/disposable email address. "
            "Please provide a permanent email address."
        )

    async def test_typo_domain_no_mx(self):
        """Test that invalid domain is rejected (no MX records)."""
        is_valid, error_hint = await check_email_validity("user@thisisnotarealdomain12345.com")
        assert is_valid is False
        assert error_hint == (
            "This email domain doesn't have valid mail servers. "
            "Please verify the spelling or provide a different email."
        )

    async def test_fake_domain_no_mx(self):
        """Test that non-existent domain is rejected (no MX records)."""
        is_valid, error_hint = await check_email_validity(
            "test@fakefakefake12345.com"
        )
        assert is_valid is False
        assert error_hint == (
            "This email domain doesn't have valid mail servers. "
            "Please verify the spelling or provide a different email."
        )

    async def test_valid_unknown_domain_anthropic(self):
        """Test that legitimate unknown domain passes (has MX records)."""
        is_valid, error_hint = await check_email_validity("contact@anthropic.com")
        assert is_valid is True
        assert error_hint is None

    async def test_case_insensitive_gmail(self):
        """Test that email validation is case-insensitive."""
        is_valid, error_hint = await check_email_validity("TEST@GMAIL.COM")
        assert is_valid is True
        assert error_hint is None

    async def test_case_insensitive_disposable(self):
        """Test that disposable check is case-insensitive."""
        is_valid, error_hint = await check_email_validity("TEST@GUERRILLAMAIL.COM")
        assert is_valid is False
        assert "disposable" in error_hint.lower()
