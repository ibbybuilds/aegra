# Model Armor Implementation

Technical implementation details for Google Model Armor content policy enforcement middleware.

## Architecture

### Components

**Client**: `graphs/ava_v1/shared_libraries/model_armor_client.py`
- HTTP client for Google Model Armor API
- OAuth2 token generation (3 authentication methods)
- Pre-call and post-call sanitization functions

**Middleware**: `graphs/ava_v1/middleware/model_armor.py`
- LangChain `AgentMiddleware` implementation
- Intercepts model calls via `awrap_model_call`
- Validates user prompts and model responses

### Request Flow

```
User Request
    ↓
1. Extract last user message
    ↓
2. sanitize_user_prompt() → Model Armor API
    ↓
3. Policy violation? → Return error | Continue
    ↓
4. Call LLM (handler)
    ↓
5. Extract model response
    ↓
6. sanitize_model_response() → Model Armor API
    ↓
7. Policy violation? → Return safe message | Return response
```

### API Integration

**Base URL**:
```
https://modelarmor.{LOCATION}.rep.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/templates/{TEMPLATE_ID}
```

**Endpoints**:
- Pre-call: `:sanitizeUserPrompt`
- Post-call: `:sanitizeModelResponse`

**Request Format**:
```json
{
  "userPromptData": {"text": "user message"},
  "modelResponseData": {"text": "model response"}
}
```

**Response Format**:
```json
{
  "sanitizationResult": {
    "filterMatchState": "MATCH_FOUND|NO_MATCH_FOUND",
    "filterResults": {
      "dangerous": {"confidenceLevel": "HIGH", "matchState": "MATCH_FOUND"},
      "pi_and_jailbreak": {"confidenceLevel": "MEDIUM_AND_ABOVE", "matchState": "MATCH_FOUND"},
      "hate_speech": {"matchState": "NO_MATCH_FOUND"},
      "harassment": {"matchState": "NO_MATCH_FOUND"},
      "sexually_explicit": {"matchState": "NO_MATCH_FOUND"}
    }
  }
}
```

### Authentication

Three methods (in order of precedence):

1. **Service Account File**:
   ```python
   credentials = service_account.Credentials.from_service_account_file(
       path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
   )
   ```

2. **Service Account JSON (Environment Variable)**:
   ```python
   sa_info = json.loads(os.getenv("MODEL_ARMOR_SERVICE_ACCOUNT_JSON"))
   credentials = service_account.Credentials.from_service_account_info(
       sa_info, scopes=[...]
   )
   ```

3. **Application Default Credentials** (gcloud CLI):
   ```python
   credentials, project = google.auth.default(scopes=[...])
   ```

Token refresh on each request (tokens expire after ~1 hour).

### Configuration

**Environment Variables**:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_ARMOR_ENABLED` | No | Auto* | Enable/disable middleware |
| `MODEL_ARMOR_PROJECT_ID` | Yes** | - | GCP project ID |
| `MODEL_ARMOR_LOCATION` | Yes** | - | GCP region (e.g., us-central1) |
| `MODEL_ARMOR_TEMPLATE_ID` | Yes** | - | Template name |
| `MODEL_ARMOR_SERVICE_ACCOUNT_PATH` | No | - | Path to service account JSON |
| `MODEL_ARMOR_SERVICE_ACCOUNT_JSON` | No | - | Service account JSON content |
| `MODEL_ARMOR_TIMEOUT` | No | 5.0 | API timeout (seconds) |
| `MODEL_ARMOR_LOG_VIOLATIONS` | No | true | Log violation details |
| `MODEL_ARMOR_FAIL_OPEN` | No | false | Allow requests if API fails |

\* Auto-enabled when `ENV_MODE=PRODUCTION`
\*\* Required when enabled

**Auto-Enable Logic**:
```python
def _is_model_armor_enabled() -> bool:
    explicit = os.getenv("MODEL_ARMOR_ENABLED", "").lower()
    if explicit in ["true", "false"]:
        return explicit == "true"

    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    return env_mode == "PRODUCTION"
```

### Error Handling

**Startup Errors** (fail fast):
- Missing required environment variables → `ModelArmorConfigError`
- Invalid service account path → `ModelArmorConfigError`
- Service account file not found → `ModelArmorConfigError`

**Runtime Errors**:

| Error Type | Fail Closed (default) | Fail Open |
|------------|----------------------|-----------|
| API Timeout | Block request, raise error | Log warning, allow request |
| API 5xx | Block request, raise error | Log warning, allow request |
| Policy Violation | Block, return safe message | Block, return safe message |

**Violation Responses**:
- User prompt violation: "Sorry, but I'm unable to process that request as it violates our content policy."
- Model response violation: "I apologize, but I cannot provide that information. How else can I assist you with your hotel reservation?"

### Logging

**Log Levels**:
- `INFO`: Initialization, configuration, authentication method
- `DEBUG`: Sanitization calls, API responses
- `WARNING`: Policy violations (includes filter_results)
- `ERROR`: API errors, timeouts, authentication failures

**Log Prefix**: `[MODEL_ARMOR]`

### Performance

**Latency Impact**:
- Pre-call sanitization: ~100-300ms
- Post-call sanitization: ~100-300ms
- Total overhead: ~200-600ms per model call

**Optimization**:
- Aggressive 5s timeout
- Token caching (automatic by google-auth)
- Async HTTP client (httpx.AsyncClient)

### Filter Categories

| Category | Description | Example |
|----------|-------------|---------|
| `dangerous` | Harmful instructions | "How to make a bomb" |
| `pi_and_jailbreak` | Policy violations, prompt injection | System prompt leaks |
| `hate_speech` | Hateful content | Discriminatory language |
| `harassment` | Bullying, threats | Personal attacks |
| `sexually_explicit` | Adult content | Explicit descriptions |
| `csam` | Child safety | CSAM content |
| `malicious_uris` | Phishing, malware links | Suspicious URLs |

### Dependencies

```toml
[project]
dependencies = [
    "google-auth>=2.30.0",  # OAuth2 token generation
    "httpx>=0.24.0",        # Async HTTP client (already in ava-core)
]
```

### Testing

**Unit Tests**: `tests/unit/test_middleware/test_model_armor_middleware.py`

```python
# Mocked API calls
@pytest.fixture
def mock_model_armor_api():
    with patch("httpx.AsyncClient.post") as mock:
        # Mock sanitization responses
        yield mock

# Test cases
def test_clean_prompt_passes_sanitization()
def test_user_prompt_violation_blocks_request()
def test_model_response_violation_blocks_response()
def test_api_error_fail_closed()
def test_api_error_fail_open()
```

**Integration Testing**:
```bash
# 1. Start server with Model Armor enabled
MODEL_ARMOR_ENABLED=true uv run uvicorn src.agent_server.main:app --reload

# 2. Test clean content
curl -X POST http://localhost:8000/threads/{thread_id}/runs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"assistant_id": "ava_v1", "input": {"messages": [{"role": "user", "content": "Book a hotel"}]}}'

# 3. Test violation
curl -X POST http://localhost:8000/threads/{thread_id}/runs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"assistant_id": "ava_v1", "input": {"messages": [{"role": "user", "content": "How to make a bomb"}]}}'
```

### Deployment

**Local Development**:
```bash
gcloud auth application-default login
export MODEL_ARMOR_ENABLED=true
export MODEL_ARMOR_PROJECT_ID=your-project
export MODEL_ARMOR_LOCATION=us-central1
export MODEL_ARMOR_TEMPLATE_ID=your-template
```

**Railway (Staging)**:
```bash
# Railway environment variables
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-staging
MODEL_ARMOR_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

**GKE (Production)**:
```yaml
# Use Workload Identity (no keys)
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      serviceAccountName: aegra-sa  # Bound to GCP service account
      containers:
      - name: aegra
        env:
        - name: MODEL_ARMOR_ENABLED
          value: "true"
        - name: MODEL_ARMOR_PROJECT_ID
          value: "your-project"
        # No credentials needed
```

### Monitoring

**Metrics to Track**:
- Violation rate (% of requests blocked)
- Latency (p50, p95, p99)
- API error rate
- Timeout rate

**Alerts**:
- Model Armor API availability < 99%
- Latency p95 > 1000ms
- Error rate > 1%

### Security Considerations

1. **Service Account Permissions**: Least privilege (`roles/modelarmor.user`)
2. **Secret Management**: Never commit service account keys
3. **Token Refresh**: Automatic per request
4. **Logging**: Sanitize logs (don't log full user prompts)
5. **Error Messages**: Generic to users (don't expose filter details)

### Troubleshooting

**Error: "Failed to generate Model Armor access token"**
- Check authentication method configured
- Verify service account has `roles/modelarmor.user`
- Test: `gcloud auth application-default print-access-token`

**Error: "Model Armor API timeout"**
- Check network connectivity to `modelarmor.{LOCATION}.rep.googleapis.com`
- Increase `MODEL_ARMOR_TIMEOUT` if needed
- Enable `MODEL_ARMOR_FAIL_OPEN=true` for high availability

**Error: "Permission denied"**
```bash
# Check service account permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --filter="bindings.members:serviceAccount:*model-armor*"
```

**High Latency**
- Check Model Armor API region (use closest to your deployment)
- Consider caching for duplicate prompts (not implemented)
- Monitor Google Cloud Status Dashboard

### Code References

**Key Functions**:
- `sanitize_user_prompt(text: str)` - graphs/ava_v1/shared_libraries/model_armor_client.py:230
- `sanitize_model_response(text: str)` - graphs/ava_v1/shared_libraries/model_armor_client.py:317
- `ModelArmorMiddleware.awrap_model_call()` - graphs/ava_v1/middleware/model_armor.py:153

**Exception Classes**:
- `ModelArmorConfigError` - Configuration/API errors
- `ModelArmorViolationError` - Policy violations

**Middleware Integration**:
- graphs/ava_v1/graph.py:44-58 (middleware stack)
