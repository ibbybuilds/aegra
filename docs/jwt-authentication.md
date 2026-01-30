# JWT Authentication

This guide covers JWT (JSON Web Token) authentication in aegra, including configuration, token generation, and integration with conversation-relay.

## Overview

Aegra supports JWT authentication using the HS256 (HMAC-SHA256) symmetric signing algorithm. This provides:

- **Sub-1ms latency** for authenticated requests (with caching)
- **Shared secret** authentication between services
- **Multi-tenant** user scoping
- **Standard JWT claims** for user identity and permissions

## Architecture

```
conversation-relay                    aegra
     │                                  │
     ├─ Generate JWT ──────────────────>│
     │  (signed with shared secret)     │
     │                                  ├─ Extract Bearer token
     │                                  ├─ Verify signature (cached)
     │                                  ├─ Map claims to user context
     │                                  └─ Scope data to user
     │
     └─ Make API request with JWT ─────>│
        Authorization: Bearer <token>
```

### Performance Characteristics

- **First request (cache miss)**: 3-5ms (HMAC signature verification)
- **Subsequent requests (cache hit)**: <0.5ms (LRU cache lookup)
- **Expected cache hit rate**: >80% (services reuse tokens)
- **Cache size**: 1000 tokens (~0.5MB memory footprint)

## Configuration

### Environment Variables

Configure these environment variables for JWT authentication:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH_TYPE` | Yes | `noop` | Set to `custom` to enable JWT auth |
| `AEGRA_JWT_SECRET` | Yes | - | Shared secret for signing/verifying tokens (256-bit) |
| `AEGRA_JWT_ISSUER` | Yes | - | Expected token issuer (e.g., `conversation-relay`) |
| `AEGRA_JWT_AUDIENCE` | Yes | - | Expected token audience (e.g., `aegra`) |
| `AEGRA_JWT_ALGORITHM` | No | `HS256` | Signing algorithm (only HS256 supported) |
| `AEGRA_JWT_VERIFY_EXPIRATION` | No | `true` | Validate token expiration |
| `AEGRA_JWT_LEEWAY_SECONDS` | No | `30` | Clock skew tolerance in seconds |

### Generate a Secure Secret

**IMPORTANT**: Use a cryptographically secure 256-bit secret:

```bash
# Generate a secure secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Example output:
# zJ3kW9pLqR8vYx2nM5tU7wA4bC6dE8fH
```

### Development Configuration

For local development, add to your `.env` file:

```bash
# Enable JWT authentication
AUTH_TYPE=custom

# JWT Configuration (Development)
AEGRA_JWT_ALGORITHM=HS256
AEGRA_JWT_SECRET=dev-secret-change-in-production-use-256-bit-key
AEGRA_JWT_ISSUER=conversation-relay-dev
AEGRA_JWT_AUDIENCE=aegra-dev
AEGRA_JWT_VERIFY_EXPIRATION=true
AEGRA_JWT_LEEWAY_SECONDS=30
```

### Staging Configuration (Railway)

Configure in Railway dashboard as environment variables:

```bash
AUTH_TYPE=custom
AEGRA_JWT_ALGORITHM=HS256
AEGRA_JWT_SECRET=<GENERATE-STAGING-SECRET>
AEGRA_JWT_ISSUER=conversation-relay-staging
AEGRA_JWT_AUDIENCE=aegra-staging
AEGRA_JWT_VERIFY_EXPIRATION=true
AEGRA_JWT_LEEWAY_SECONDS=30
```

### Production Configuration (GKE)

Store `AEGRA_JWT_SECRET` in GCP Secret Manager:

```bash
# Create secret in GCP Secret Manager
echo -n "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" | \
  gcloud secrets create jwt-secret --data-file=-

# Reference in Kubernetes manifest
AUTH_TYPE=custom
AEGRA_JWT_ALGORITHM=HS256
AEGRA_JWT_SECRET=<from-secret-manager>
AEGRA_JWT_ISSUER=conversation-relay
AEGRA_JWT_AUDIENCE=aegra
AEGRA_JWT_VERIFY_EXPIRATION=true
AEGRA_JWT_LEEWAY_SECONDS=30
```

## Token Format

### JWT Claims

Required claims:
- `sub` (string): Subject (user identifier) - maps to `identity`
- `iss` (string): Issuer - must match `AEGRA_JWT_ISSUER`
- `aud` (string): Audience - must match `AEGRA_JWT_AUDIENCE`
- `iat` (number): Issued at timestamp
- `exp` (number): Expiration timestamp

Optional claims:
- `name` (string): User display name - maps to `display_name`
- `email` (string): User email address - maps to `email`
- `org` (string): Organization ID - maps to `org_id`
- `scopes` (array): ⚠️ **Ignored** - permissions come from issuer mapping (see Security Model)

### Example Token Payload

```json
{
  "sub": "user-123",
  "name": "John Doe",
  "email": "john@example.com",
  "org": "acme-corp",
  "scopes": ["read", "write"],
  "iss": "conversation-relay",
  "aud": "aegra",
  "iat": 1705932000,
  "exp": 1705933800
}
```

### Token Expiration Recommendations

- **Development**: 1 hour (3600s)
- **Staging**: 30 minutes (1800s)
- **Production**: 30 minutes (1800s)
- **Leeway**: 30 seconds (clock skew tolerance)

## Generating Test Tokens

Aegra includes a token generation utility for local development and testing.

### Basic Usage

```bash
# Generate token with minimal claims
uv run python scripts/generate_jwt_token.py --sub test-user

# Generate token with all optional claims
uv run python scripts/generate_jwt_token.py \
  --sub user-123 \
  --name "John Doe" \
  --email "john@example.com" \
  --org "acme-corp" \
  --scopes "read" "write"

# Generate token with 24-hour expiration
uv run python scripts/generate_jwt_token.py \
  --sub test-user \
  --exp 86400

# Output with Bearer prefix for direct use in curl
uv run python scripts/generate_jwt_token.py \
  --sub test-user \
  --output-bearer
```

### Test with curl

```bash
# Generate token
TOKEN=$(AEGRA_JWT_SECRET=dev-secret AEGRA_JWT_ISSUER=test-issuer AEGRA_JWT_AUDIENCE=test-audience \
  uv run python scripts/generate_jwt_token.py --sub test-user)

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/threads
```

## Security Model

### Issuer-Based Scope Mapping

Aegra uses **server-side scope enforcement** to prevent services from self-assigning elevated privileges. Instead of trusting the `scopes` claim in JWT tokens, aegra maps the `iss` (issuer) claim to allowed scopes.

**How it works:**

1. Service generates JWT with its issuer identifier (e.g., `"iss": "conversation-relay"`)
2. Service can include any `scopes` claim in the token (these are **ignored**)
3. Aegra verifies the token signature and issuer
4. Aegra looks up allowed scopes based on **issuer only** (server-defined mapping)
5. Service gets only the scopes defined in aegra's configuration

**Default Issuer-Scope Mapping:**

| Issuer | Allowed Scopes | Access Level |
|--------|----------------|--------------|
| `conversation-relay` | `admin` | Full access to all operations for all users |
| `transcript-service` | `read:all` | Read access to all resources for all users |
| Other issuers | `[]` (empty) | User-scoped access only (can only access own resources) |

**Configuration:**

The mapping is defined in `auth.py` and can be overridden via the `AEGRA_JWT_ISSUER_SCOPES` environment variable for testing:

```bash
# Production: hardcoded in auth.py (default)
# No environment variable needed

# Testing: override via environment
AEGRA_JWT_ISSUER_SCOPES="service1:admin;service2:read:all;service3:write:all"
```

**Why This is Secure:**

- Services cannot escalate their own privileges (token scopes are ignored)
- Each service's permissions are controlled by aegra's configuration
- Even if a service is compromised, it cannot grant itself admin access
- Adding new services requires updating aegra's configuration (deployment)

**Example:**

```python
# conversation-relay generates token with admin claims
payload = {
    "sub": "conversation-relay",
    "iss": "conversation-relay",
    "scopes": ["admin", "super-secret-scope"],  # Included but ignored
    # ...
}

# After verification, aegra assigns scopes based ONLY on issuer:
# → permissions = ["admin"]  (from issuer mapping, not from token)
```

### Multi-Tenant Isolation

Regular users (not in the issuer-scope map) are **automatically scoped** to their own resources:

- Users can only access threads, runs, and state they created
- Owner filters are applied transparently at the database level
- No cross-tenant data leakage

Admin users (with `admin`, `read:all`, or `write:all` scopes) **bypass** user-scoping:

- Can access resources for **any user**
- Used by conversation-relay for managing user conversations
- Used by transcript-service for reading conversation histories

## conversation-relay Integration

### Token Generation (conversation-relay side)

```python
import jwt
import os
from datetime import datetime, timedelta, timezone

def generate_aegra_token(user_id: str, org_id: str) -> str:
    """Generate JWT token for aegra API calls."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org": org_id,
        "iss": os.getenv("AEGRA_JWT_ISSUER"),
        "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=1800)).timestamp()),  # 30 min
    }
    
    return jwt.encode(
        payload,
        os.getenv("AEGRA_JWT_SECRET"),
        algorithm="HS256"
    )
```

### Making API Calls

```python
import httpx

async def call_aegra_api(user_id: str, org_id: str):
    """Make authenticated call to aegra API."""
    token = generate_aegra_token(user_id, org_id)
    
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.post(
            "https://aegra.example.com/threads",
            headers=headers,
        )
        return response.json()
```

### Environment Synchronization

**CRITICAL**: Both services must use the same JWT configuration:

| Variable | conversation-relay | aegra |
|----------|-------------------|--------|
| `AEGRA_JWT_SECRET` | ✅ MUST MATCH | ✅ MUST MATCH |
| `AEGRA_JWT_ISSUER` | ✅ MUST MATCH | ✅ MUST MATCH |
| `AEGRA_JWT_AUDIENCE` | ✅ MUST MATCH | ✅ MUST MATCH |
| `AEGRA_JWT_ALGORITHM` | HS256 | HS256 |

## Multi-Tenant Isolation

JWT authentication automatically provides user-scoped data isolation:

### How It Works

1. **Authentication**: JWT is verified and claims are extracted
2. **User Context**: Claims are mapped to `MinimalUserDict`:
   ```python
   {
       "identity": "user-123",        # from 'sub' claim
       "org_id": "acme-corp",         # from 'org' claim
       "display_name": "John Doe",    # from 'name' claim
       "email": "john@example.com",   # from 'email' claim
       "permissions": ["read", "write"], # from 'scopes' claim
       "is_authenticated": True
   }
   ```
3. **Authorization**: Resources are filtered by `owner` field:
   ```python
   # Only return threads owned by authenticated user
   {"owner": "user-123"}
   ```
4. **Metadata Injection**: New resources get owner automatically:
   ```python
   # When creating thread, metadata is injected
   {"metadata": {"owner": "user-123"}}
   ```

### Isolation Guarantees

- ✅ Users can only access their own threads
- ✅ Users can only access their own runs
- ✅ Thread listing is scoped to user
- ✅ Run listing is scoped to user
- ✅ Organization-level isolation via `org_id`

## Security Considerations

### Secret Management

**Development**:
- Store in `.env` file (not committed to git)
- Use test secret like `dev-secret-change-in-production`
- Acceptable risk for local testing

**Staging**:
- Store in Railway environment variables
- Generate new secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Never commit to git

**Production**:
- Store in GCP Secret Manager
- Rotate quarterly
- Use separate secret from staging
- Never commit to git or logs

### Token Security

- **HTTPS Only**: Always use HTTPS in production (prevents token theft)
- **Short Expiration**: 30-minute tokens limit replay attack window
- **Clock Skew**: 30-second leeway handles time sync issues
- **Signature Verification**: HMAC-SHA256 prevents tampering

### Attack Mitigation

| Attack | Mitigation |
|--------|-----------|
| Token replay | 30-minute expiration + HTTPS |
| Token theft | HTTPS + short expiration |
| Brute force | HMAC-SHA256 cryptographic security |
| Clock skew | 30-second leeway tolerance |

## Troubleshooting

### Common Errors

#### "Authorization header required"

**Cause**: Missing `Authorization` header in request

**Fix**: Include header in all requests:
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/threads
```

#### "Invalid token signature"

**Cause**: `AEGRA_JWT_SECRET` mismatch between services

**Fix**: Verify both services use identical `AEGRA_JWT_SECRET`:
```bash
# Check conversation-relay secret
echo $AEGRA_JWT_SECRET

# Check aegra secret (in Railway/K8s config)
```

#### "Invalid token issuer"

**Cause**: Token `iss` claim doesn't match `AEGRA_JWT_ISSUER`

**Fix**: Ensure conversation-relay sets correct issuer:
```python
payload = {
    "iss": os.getenv("AEGRA_JWT_ISSUER"),  # Must match aegra's AEGRA_JWT_ISSUER
    ...
}
```

#### "Invalid token audience"

**Cause**: Token `aud` claim doesn't match `AEGRA_JWT_AUDIENCE`

**Fix**: Ensure conversation-relay sets correct audience:
```python
payload = {
    "aud": os.getenv("AEGRA_JWT_AUDIENCE"),  # Must match aegra's AEGRA_JWT_AUDIENCE
    ...
}
```

#### "Token expired"

**Cause**: Token `exp` claim is in the past

**Fix**: Generate new token with valid expiration:
```python
exp = int((datetime.now(timezone.utc) + timedelta(seconds=1800)).timestamp())
```

#### "Token missing 'sub' claim"

**Cause**: JWT payload doesn't include `sub` (subject) claim

**Fix**: Always include `sub` in token payload:
```python
payload = {
    "sub": user_id,  # REQUIRED
    ...
}
```

### Performance Issues

#### "Authentication is slow (>5ms)"

**Check**:
1. Verify caching is enabled (check `get_jwt_cache_info()`)
2. Ensure same token is reused across requests
3. Check cache hit rate (should be >80%)

**Debug**:
```python
from src.agent_server.core.jwt_utils import get_jwt_cache_info

info = get_jwt_cache_info()
print(f"Cache hits: {info['hits']}")
print(f"Cache misses: {info['misses']}")
print(f"Hit rate: {info['hits'] / (info['hits'] + info['misses']) * 100:.1f}%")
```

### Configuration Validation

Verify JWT configuration:

```bash
# Check environment variables
uv run python -c "
import os
from src.agent_server.core.jwt_utils import validate_jwt_configuration

try:
    validate_jwt_configuration()
    print('✓ JWT configuration is valid')
except Exception as e:
    print(f'✗ Configuration error: {e}')
"
```

## Testing

### Unit Tests

```bash
# Run JWT utils tests
uv run pytest tests/unit/test_core/test_jwt_utils.py -v

# Run auth integration tests
uv run pytest tests/unit/test_auth_jwt.py -v
```

### E2E Tests

```bash
# Run E2E JWT auth flow tests (requires AUTH_TYPE=custom)
AUTH_TYPE=custom \
AEGRA_JWT_SECRET=test-secret \
AEGRA_JWT_ISSUER=test-issuer \
AEGRA_JWT_AUDIENCE=test-audience \
uv run pytest tests/e2e/test_jwt_auth_flow.py -v
```

### Manual Testing

```bash
# 1. Start aegra with JWT auth
AUTH_TYPE=custom \
AEGRA_JWT_SECRET=test-secret \
AEGRA_JWT_ISSUER=test-issuer \
AEGRA_JWT_AUDIENCE=test-audience \
docker compose up aegra

# 2. Generate test token
TOKEN=$(AEGRA_JWT_SECRET=test-secret AEGRA_JWT_ISSUER=test-issuer AEGRA_JWT_AUDIENCE=test-audience \
  uv run python scripts/generate_jwt_token.py --sub test-user)

# 3. Test authenticated endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/threads

# 4. Test user scoping
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/threads
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/threads
```

## Migration Guide

### From noop to JWT Auth

1. **Generate shared secret**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Update aegra configuration**:
   ```bash
   AUTH_TYPE=custom
   AEGRA_JWT_SECRET=<generated-secret>
   AEGRA_JWT_ISSUER=conversation-relay
   AEGRA_JWT_AUDIENCE=aegra
   ```

3. **Update conversation-relay configuration**:
   ```bash
   AEGRA_JWT_SECRET=<same-as-aegra>
   AEGRA_JWT_ISSUER=conversation-relay
   AEGRA_JWT_AUDIENCE=aegra
   ```

4. **Update conversation-relay code**:
   ```python
   # Add JWT generation
   import jwt
   from datetime import datetime, timedelta, timezone
   
   def generate_token(user_id: str) -> str:
       now = datetime.now(timezone.utc)
       payload = {
           "sub": user_id,
           "iss": os.getenv("AEGRA_JWT_ISSUER"),
           "aud": os.getenv("AEGRA_JWT_AUDIENCE"),
           "iat": int(now.timestamp()),
           "exp": int((now + timedelta(seconds=1800)).timestamp()),
       }
       return jwt.encode(payload, os.getenv("AEGRA_JWT_SECRET"), algorithm="HS256")
   
   # Include in API calls
   headers = {"Authorization": f"Bearer {generate_token(user_id)}"}
   ```

5. **Test integration**:
   ```bash
   # Verify tokens are accepted
   # Verify user scoping works
   # Monitor authentication latency
   ```

## References

- [JWT.io](https://jwt.io/) - JWT debugging and information
- [RFC 7519](https://tools.ietf.org/html/rfc7519) - JWT specification
- [PyJWT Documentation](https://pyjwt.readthedocs.io/) - Python JWT library
- [HMAC-SHA256](https://en.wikipedia.org/wiki/HMAC) - Signing algorithm

## Support

For issues or questions:
- Check troubleshooting section above
- Review test files for examples
- Check application logs for detailed error messages
- Verify environment configuration matches between services
