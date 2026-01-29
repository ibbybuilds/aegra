# Email Validation Implementation Plan

## Overview

Implement cost-optimized email validation for the `update_customer_details` tool using a tiered approach. Free checks run first (syntax, disposable domains, MX records, trusted providers), followed by CRM lookup for repeat customers, with paid IPQS API only used for unknown domains from first-time customers.

**Goal**: Minimize IPQS API costs while maintaining security and preventing fraudulent bookings.

---

## Cost Optimization Strategy

### Three-Tier Validation Approach

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: FREE CHECKS (always run first, no API calls)       │
├─────────────────────────────────────────────────────────────┤
│ 1. Syntax validation (regex)                               │
│ 2. Disposable domain blocklist (~5,000 domains)            │
│ 3. MX record validation (DNS lookup)                       │
│ 4. Trusted provider whitelist (Gmail, Yahoo, etc.)         │
│    └─> If trusted → ACCEPT & SKIP IPQS ✓                   │
└─────────────────────────────────────────────────────────────┘
                          ↓ (if not trusted)
┌─────────────────────────────────────────────────────────────┐
│ Tier 2: CRM LOOKUP (free, external API)                    │
├─────────────────────────────────────────────────────────────┤
│ 5. Check if email exists in booking history                │
│    └─> If repeat customer → ACCEPT & SKIP IPQS ✓           │
└─────────────────────────────────────────────────────────────┘
                          ↓ (if new customer)
┌─────────────────────────────────────────────────────────────┐
│ Tier 3: IPQS API (paid, only for unknowns)                 │
├─────────────────────────────────────────────────────────────┤
│ 6. Call IPQualityScore API for fraud detection             │
│    • fraud_score > 80 → REJECT                             │
│    • smtp_score == -1 → REJECT (email doesn't exist)       │
│    • disposable == true → REJECT (backup check)            │
│    • deliverability == "low" → REJECT                      │
│    • recent_abuse == true → REJECT                         │
│    • created < 24 hours → REJECT                           │
│    • API fails/timeout → ACCEPT (free checks passed)       │
└─────────────────────────────────────────────────────────────┘
```

**Expected IPQS usage reduction**: ~80-90% (most emails are Gmail/Yahoo or repeat customers)

---

## Implementation Tasks

### Task 1: Download Disposable Domain Blocklist

**File**: `graphs/ava_v1/shared_libraries/disposable_email_blocklist.txt`

**Source**: https://github.com/disposable-email-domains/disposable-email-domains/blob/master/disposable_email_blocklist.conf

**Action**:
```bash
cd graphs/ava_v1/shared_libraries
curl -o disposable_email_blocklist.txt https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf
```

**Commit**: Include this file in the repo (it's a static list, updated periodically)

**Update strategy**: Refresh monthly or when new disposable services are discovered

---

### Task 2: Add dnspython Dependency

**File**: `pyproject.toml`

**Command**:
```bash
uv add dnspython
```

**Purpose**: DNS lookups for MX record validation

---

### Task 3: Create Email Validation Module

**File**: `graphs/ava_v1/shared_libraries/email_validator.py`

**Functions to implement**:

#### 1. `is_disposable_domain(domain: str) -> bool`

Check if email domain is in disposable blocklist.

**Implementation**:
```python
import os
from pathlib import Path

# Module-level cache (load once)
_DISPOSABLE_DOMAINS: set[str] | None = None

def _load_disposable_domains() -> set[str]:
    """Load disposable domain blocklist from file (cached)."""
    global _DISPOSABLE_DOMAINS
    if _DISPOSABLE_DOMAINS is None:
        blocklist_path = Path(__file__).parent / "disposable_email_blocklist.txt"
        with open(blocklist_path, "r") as f:
            _DISPOSABLE_DOMAINS = {line.strip().lower() for line in f if line.strip()}
    return _DISPOSABLE_DOMAINS

def is_disposable_domain(domain: str) -> bool:
    """Check if domain is in disposable email blocklist."""
    blocklist = _load_disposable_domains()
    return domain.lower() in blocklist
```

---

#### 2. `has_valid_mx_records(domain: str) -> bool`

Check if domain has MX records (can receive email).

**Implementation**:
```python
import logging
import dns.resolver

logger = logging.getLogger(__name__)

def has_valid_mx_records(domain: str) -> bool:
    """Check if domain has MX records via DNS lookup."""
    try:
        # Set 5 second timeout for DNS query
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 5.0

        # Query MX records
        mx_records = resolver.resolve(domain, 'MX')
        return len(mx_records) > 0

    except dns.resolver.NXDOMAIN:
        # Domain doesn't exist
        logger.info(f"[EMAIL_VALIDATOR] Domain does not exist: {domain}")
        return False

    except dns.resolver.NoAnswer:
        # No MX records found
        logger.info(f"[EMAIL_VALIDATOR] No MX records for domain: {domain}")
        return False

    except dns.exception.Timeout:
        # DNS timeout - fail open (assume valid to avoid false rejection)
        logger.warning(f"[EMAIL_VALIDATOR] DNS timeout for domain: {domain}, assuming valid")
        return True

    except Exception as e:
        # Unexpected error - fail open
        logger.error(f"[EMAIL_VALIDATOR] DNS error for domain {domain}: {e}, assuming valid")
        return True
```

---

#### 3. `is_trusted_provider(domain: str) -> bool`

Check if domain is a major trusted email provider.

**Implementation**:
```python
# Major trusted email providers (expand as needed)
TRUSTED_PROVIDERS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "aol.com",
    "live.com",
    "msn.com",
    "protonmail.com",
    "mail.com",
}

def is_trusted_provider(domain: str) -> bool:
    """Check if domain is a major trusted email provider."""
    return domain.lower() in TRUSTED_PROVIDERS
```

**Note**: Expand this list based on traffic analysis. Consider adding regional providers.

---

#### 4. `check_repeat_customer(email: str) -> bool`

**STATUS**: ⚠️ PENDING - Requires CRM API endpoint details

**Placeholder implementation**:
```python
async def check_repeat_customer(email: str) -> bool:
    """Check if customer email exists in booking history.

    TODO: Implement CRM API integration
    Requires: CRM endpoint details (see CRM Integration section below)

    Args:
        email: Customer email address

    Returns:
        True if customer has previous bookings, False if new customer
    """
    # TODO: Implement CRM lookup when endpoint available
    logger.debug(f"[EMAIL_VALIDATOR] CRM lookup not implemented, treating as new customer")
    return False
```

**When CRM endpoint is available**:
1. Make async HTTP request to CRM endpoint with email
2. Parse response to check if customer exists
3. Handle errors gracefully (return `False` if CRM unavailable)
4. Add caching (Redis) to avoid repeated lookups
5. Log lookup results for monitoring

---

#### 5. `validate_email_with_ipqs(email: str) -> dict | None`

Call IPQualityScore API and return raw response.

**Implementation**:
```python
import os
import logging
from urllib.parse import quote
import httpx

logger = logging.getLogger(__name__)

IPQS_API_KEY = os.getenv("IPQUALITYSCORE_API_KEY", None)
IPQS_TIMEOUT = 20  # Recommended for full SMTP validation

async def validate_email_with_ipqs(email: str) -> dict | None:
    """Call IPQualityScore API to validate email address.

    Args:
        email: Email address to validate

    Returns:
        Dict with API response if successful, None if API unavailable/failed
    """
    if not IPQS_API_KEY:
        logger.debug("[EMAIL_VALIDATOR] IPQS API key not configured, skipping API call")
        return None

    try:
        # URL-encode email
        encoded_email = quote(email)
        url = f"https://www.ipqualityscore.com/api/json/email/{IPQS_API_KEY}/{encoded_email}"

        # Make API request
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"timeout": IPQS_TIMEOUT, "fast": "false"},
                timeout=IPQS_TIMEOUT + 5  # Add buffer for network overhead
            )
            response.raise_for_status()

            domain = email.split('@')[1]
            logger.info(f"[EMAIL_VALIDATOR] IPQS API success for domain: {domain}")
            return response.json()

    except httpx.TimeoutException:
        domain = email.split('@')[1]
        logger.warning(f"[EMAIL_VALIDATOR] IPQS API timeout for domain: {domain}")
        return None

    except httpx.HTTPStatusError as e:
        domain = email.split('@')[1]
        logger.error(f"[EMAIL_VALIDATOR] IPQS API error for domain {domain}: {e.response.status_code}")
        return None

    except httpx.RequestError as e:
        domain = email.split('@')[1]
        logger.error(f"[EMAIL_VALIDATOR] IPQS network error for domain {domain}: {e}")
        return None

    except Exception as e:
        domain = email.split('@')[1]
        logger.error(f"[EMAIL_VALIDATOR] IPQS unexpected error for domain {domain}: {e}")
        return None
```

---

#### 6. `check_email_validity(email: str) -> Tuple[bool, str | None]`

Main validation function - runs all tiers in order.

**Implementation** (see pseudocode in plan file section for full logic)

**Key points**:
- Run Tier 1 checks first (free, fast)
- If trusted provider → Accept immediately, skip IPQS
- Check CRM for repeat customers → Skip IPQS if exists
- Only call IPQS for unknown domains from new customers
- If IPQS fails → Accept (free checks already passed)
- Return tuple: `(is_valid, error_message)`

---

### Task 4: Update `update_customer.py`

**File**: `graphs/ava_v1/tools/book/update_customer.py`

**Changes**:

1. **Add import** (after line 11):
```python
from ava_v1.shared_libraries.email_validator import check_email_validity
```

2. **Replace email validation block** (lines 64-73):

**Before**:
```python
if field == "email":
    # Simple regex for email validation
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_pattern, value.strip()):
        return json.dumps(
            {
                "status": "error",
                "message": f"Invalid email format: {value}. Please verify spelling.",
            }
        )
```

**After**:
```python
if field == "email":
    # Use tiered validation (free checks + CRM + IPQS)
    is_valid, error_hint = await check_email_validity(value.strip())
    if not is_valid:
        logger.info(f"[UPDATE_CUSTOMER] Email validation failed: {error_hint}")
        return json.dumps(
            {
                "status": "error",
                "message": error_hint,
            }
        )
    logger.info(f"[UPDATE_CUSTOMER] Email validated successfully")
```

---

### Task 5: Update Environment Configuration

**File**: `.env.example`

**Add after line 42** (after `RESERVATION_PORTAL_BASE_URL`):

```bash
# Email Validation (tiered approach for cost optimization)
# Free checks always run: syntax, disposable blocklist, MX records, trusted providers
# IPQS API only called for unknown domains from first-time customers
IPQUALITYSCORE_API_KEY=  # Get from https://www.ipqualityscore.com/user/api-keys

# CRM/Booking History API (for repeat customer check)
# TODO: Add CRM endpoint configuration when available
# CRM_API_URL=
# CRM_API_KEY=
```

**Add to your local `.env`**:
```bash
IPQUALITYSCORE_API_KEY=your-actual-api-key-here
```

---

### Task 6: Write Comprehensive Tests

**File**: `tests/unit/test_customer_workflow.py`

**Test categories** (21 tests total):

#### Tier 1: Free checks (6 tests)
1. Invalid syntax → Reject
2. Disposable domain (guerrillamail.com) → Reject
3. No MX records → Reject
4. Gmail.com → Accept without IPQS
5. Yahoo.com → Accept without IPQS
6. Outlook.com → Accept without IPQS

#### Tier 2: CRM lookup (2 tests)
7. Repeat customer → Accept without IPQS
8. New customer → Continue to IPQS

#### Tier 3: IPQS API (11 tests)
9. Valid email → Accept
10. High fraud score (85) → Reject with fraud hint
11. Non-existent (smtp_score: -1) → Reject with "doesn't exist" hint
12. Disposable (backup check) → Reject
13. Low deliverability → Reject
14. Recent abuse → Reject
15. Created < 24 hours → Reject
16. IPQS timeout → Accept (free checks passed)
17. IPQS HTTP error → Accept (free checks passed)
18. Missing API key → Skip IPQS, accept if free checks passed
19. Multiple issues → Return highest priority error

#### Integration tests (2 tests)
20. Full flow with Gmail → All tiers work correctly
21. Full flow with unknown domain → Calls IPQS

**Mock patterns**:
- Use `patch("httpx.AsyncClient")` for IPQS API mocking
- Use `patch("dns.resolver.Resolver")` for MX record mocking
- Use `patch("ava_v1.shared_libraries.email_validator.check_repeat_customer")` for CRM mocking
- Use existing `MagicMock`, `AsyncMock` patterns

---

## CRM Integration Requirements

**STATUS**: ⚠️ PENDING - Waiting for colleague to provide details

### Required Information:

1. **Endpoint URL**
   - Example: `https://api.example.com/customers/check?email={email}`
   - Or relative to `POLLING_SERVICE_URL`: `/api/customers/lookup`

2. **HTTP Method**
   - GET or POST?

3. **Request Format**
   - Query parameters: `?email=customer@example.com`
   - Or JSON body: `{"email": "customer@example.com"}`
   - Headers needed? (Authorization, API-Key, etc.)

4. **Response Format**
   - Existing customer example:
     ```json
     {
       "exists": true,
       "customer_id": "abc123",
       "booking_count": 5,
       "last_booking_date": "2025-12-15"
     }
     ```
   - New customer example:
     ```json
     {
       "exists": false
     }
     ```

5. **Authentication**
   - API key in header?
   - Bearer token?
   - Same auth as POLLING_SERVICE_URL?

6. **Error Handling**
   - What status codes indicate "not found" vs actual errors?
   - How to handle 404, 500, timeout?

### Implementation Checklist (once endpoint is available):

- [ ] Add CRM endpoint configuration to `.env.example`
- [ ] Implement `check_repeat_customer()` with real API call
- [ ] Add Redis caching (TTL: 1 hour) to avoid repeated lookups
- [ ] Write tests with mocked CRM responses
- [ ] Add error handling and logging
- [ ] Monitor CRM lookup success rate

---

## Error Messages (User-Facing)

All error messages are conversational and don't expose internal validation logic:

| Rejection Reason | Error Message |
|------------------|---------------|
| Invalid syntax | "Invalid email format" |
| Disposable domain | "This appears to be a temporary/disposable email address. Please provide a permanent email address." |
| No MX records | "This email domain doesn't have valid mail servers. Please verify the spelling or provide a different email." |
| High fraud score | "This email didn't pass our fraud check. Can you verify the spelling or provide a different email?" |
| Email doesn't exist (IPQS) | "The email doesn't exist. Maybe I misspelled it, can you please spell out your email for me?" |
| Low deliverability | "This email may not be deliverable. Can you verify the spelling or provide a different email?" |
| Recent abuse | "This email has been flagged for suspicious activity. Please provide a different email." |
| Created < 24 hours | "I see that the email was created recently. You need to provide a different email for me to make this booking." |

---

## Verification Steps

After implementation, run these checks:

### 1. Unit Tests
```bash
uv run pytest tests/unit/test_customer_workflow.py -v
```
**Expected**: All 21 new tests pass, existing tests still pass

### 2. Manual Testing (with real API key)

**Test with various email types**:
```bash
# Trusted provider (should skip IPQS)
test@gmail.com → ✅ Accept (no IPQS call)

# Disposable domain (should reject before IPQS)
test@guerrillamail.com → ❌ Reject with disposable message (no IPQS call)

# Non-existent domain (no MX records)
test@fakefakefake12345.com → ❌ Reject with MX error (no IPQS call)

# Unknown domain (should call IPQS)
test@mycompany.com → Calls IPQS API

# Invalid syntax
test@ → ❌ Reject immediately
```

### 3. Check IPQS Usage

**Monitor API call volume**:
- Before implementation: ~100% of emails
- After implementation: ~10-20% of emails (only unknowns from new customers)

**Log analysis**:
```bash
# Check how many emails skip IPQS
grep "IPQS API" logs | grep "skipping" | wc -l

# Check trusted provider matches
grep "trusted provider" logs | wc -l

# Check disposable blocks
grep "disposable" logs | wc -l
```

### 4. Performance Testing

**Expected validation times**:
- Trusted provider: <10ms (instant whitelist check)
- Disposable domain: <50ms (in-memory set lookup)
- MX record check: 50-500ms (DNS query)
- IPQS API: 2-5 seconds (only for unknowns)

---

## Edge Cases Handled

✅ **API rate limiting (429)** → Treated as API failure, accept (free checks passed)

✅ **Malformed IPQS response** → Use `.get()` with defaults, missing fields = "pass"

✅ **Email with special characters** → URL-encode using `urllib.parse.quote()`

✅ **Long emails (>254 chars)** → Pre-validate before API call

✅ **International domains (IDN)** → IPQS supports, DNS handles properly

✅ **Timestamp parsing errors** → Skip age check, don't reject

✅ **DNS timeout** → Fail open (assume valid MX records)

✅ **CRM API unavailable** → Treat as new customer, continue to IPQS

---

## Security & Privacy

🔒 **PII Protection**:
- Only log email **domain** in INFO/WARNING/ERROR logs
- Full email only in DEBUG level (disabled in production)
- Example: `logger.info(f"Validating domain: {email.split('@')[1]}")`

🔒 **API Key Security**:
- Store in environment variable only
- Never commit to repo
- Document in `.env.example` with placeholder

🔒 **Error Messages**:
- Generic, user-friendly language
- Don't expose "fraud score", "SMTP validation", "API timeout"
- Don't reveal internal business rules

🔒 **User Data**:
- Only email sent to IPQS (no other PII)
- No storage by IPQS per their documentation
- CRM lookup uses email only

---

## Monitoring & Logging

### Key Metrics to Track

1. **Validation tier distribution**:
   - % rejected at syntax check
   - % rejected at disposable check
   - % rejected at MX check
   - % accepted at trusted provider (skip IPQS)
   - % accepted at CRM check (skip IPQS)
   - % that reach IPQS API

2. **IPQS API metrics**:
   - Call volume (should be ~10-20% of total emails)
   - Success rate
   - Timeout rate
   - Rejection rate by reason

3. **Cost tracking**:
   - IPQS API calls per day
   - Estimated monthly cost
   - Cost per booking

### Log Examples

```python
# Tier 1 acceptance
logger.info(f"[EMAIL_VALIDATOR] Accepted trusted provider: {domain}")

# Tier 2 acceptance
logger.info(f"[EMAIL_VALIDATOR] Accepted repeat customer (CRM match): {domain}")

# Tier 3 rejection
logger.info(f"[EMAIL_VALIDATOR] IPQS rejection for domain {domain}: fraud_score={score}")

# IPQS skip
logger.info(f"[EMAIL_VALIDATOR] Skipping IPQS for trusted provider: {domain}")
```

---

## Rollback Plan

If issues arise in production:

### Quick Fix (No Code Changes)
```bash
# Disable IPQS API (falls back to free checks only)
IPQUALITYSCORE_API_KEY=""

# Result: Only syntax, disposable, MX, and trusted provider checks run
```

### Code Rollback
1. Revert `update_customer.py` changes
2. Keep `email_validator.py` for future use
3. Remove dnspython dependency if causing issues

### Monitoring for Issues
- High IPQS API error rate (>10%)
- High email rejection rate (>30%)
- Increased validation latency (>10 seconds)
- False positives (legitimate emails rejected)

---

## Future Enhancements (Not in Scope)

💡 **Domain reputation caching** - Cache validation results by domain

💡 **Batch validation** - Validate multiple emails in parallel

💡 **A/B testing** - Compare conversion rates with/without strict validation

💡 **Custom fraud score thresholds** - Make configurable per client

💡 **Booking amount threshold** - Only validate high-value bookings ($1000+)

💡 **Risk signal integration** - Use IP, velocity, billing mismatch to trigger IPQS

💡 **Regional provider lists** - Add country-specific trusted providers

---

## Implementation Checklist

### Prerequisites
- [x] IPQS API key obtained
- [ ] CRM API endpoint details (PENDING from colleague)

### Development Tasks
- [ ] Download disposable domain blocklist
- [ ] Add dnspython dependency (`uv add dnspython`)
- [ ] Create `email_validator.py` with all 6 functions
- [ ] Update `update_customer.py` to use new validation
- [ ] Update `.env.example` with configuration
- [ ] Write 21 unit tests
- [ ] Update `pyproject.toml` dependencies

### Testing
- [ ] All unit tests pass
- [ ] Manual testing with Gmail (trusted provider)
- [ ] Manual testing with disposable domain
- [ ] Manual testing with non-existent domain
- [ ] Manual testing with unknown domain (IPQS call)
- [ ] Verify IPQS API call reduction (~80-90%)

### Documentation
- [ ] Add inline code comments
- [ ] Update CLAUDE.md if needed
- [ ] Document CRM integration when ready

### Deployment
- [ ] Add IPQS API key to production `.env`
- [ ] Monitor initial validation metrics
- [ ] Check IPQS usage and costs
- [ ] Set up alerts for high error rates

---

## Questions for Colleague

1. **CRM API Endpoint**: Can you provide the endpoint URL, request format, and response structure for checking if a customer email exists in booking history?

2. **Domain Allowlist**: Are there any specific business email domains (e.g., `mybusiness.com`) that should be whitelisted alongside Gmail/Yahoo?

3. **Error Handling**: What should happen if both free checks and IPQS API fail? Accept or reject?

4. **Monitoring**: Do we have existing monitoring/alerting infrastructure for API usage and costs?

5. **Testing**: Do we have access to test disposable emails and known fraudulent emails for testing?

---

## Contact & Support

**IPQS Support**: (800) 713-2618 or https://www.ipqualityscore.com/user/api-keys

**Implementation Questions**: Ask in team chat or create GitHub issue

**API Docs**:
- IPQS Email Validation: https://www.ipqualityscore.com/documentation/email-validation-api/overview
- dnspython: https://dnspython.readthedocs.io/

---

## Summary

This implementation provides cost-effective email validation by:
- Running free checks first (syntax, disposable, MX, trusted providers)
- Checking CRM for repeat customers (skip expensive IPQS calls)
- Only calling paid IPQS API for unknown domains from new customers
- Gracefully handling failures (accept if free checks pass)

**Expected outcome**: ~80-90% reduction in IPQS API usage while maintaining security.
