# Model Armor Implementation Summary

This document summarizes the Google Model Armor middleware implementation for the ava_v1 graph.

## Implementation Date

February 3, 2026

## What Was Implemented

### 1. Model Armor API Client
**File**: `graphs/ava_v1/shared_libraries/model_armor_client.py`

A standalone client for interacting with Google's Model Armor API:
- Configuration validation with fail-fast error handling
- Google OAuth2 service account authentication with automatic token refresh
- Pre-call sanitization: `sanitize_user_prompt(text)`
- Post-call sanitization: `sanitize_model_response(text)`
- Feature flag support with auto-enable in production
- Configurable timeout, logging, and fail-open/fail-closed modes

### 2. Model Armor Middleware
**File**: `graphs/ava_v1/middleware/model_armor.py`

LangChain AgentMiddleware implementation:
- Intercepts all LLM calls in ava_v1 graph
- Extracts last user message from request (supports multimodal content)
- Checks user prompt before model call (blocks if violation)
- Checks model response after model call (blocks if violation)
- Returns safe, generic error messages on violations
- Respects fail-open/fail-closed configuration

### 3. Middleware Reorganization
**Changes**:
- Moved `graphs/ava_v1/middleware.py` → `graphs/ava_v1/middleware/__init__.py`
- Created `graphs/ava_v1/middleware/` directory structure
- Updated imports in `graphs/ava_v1/graph.py`
- Added `ModelArmorMiddleware()` as last middleware in stack

### 4. Configuration
**File**: `.env.example`

Added 8 new environment variables:
```bash
MODEL_ARMOR_ENABLED=false
MODEL_ARMOR_PROJECT_ID=your-gcp-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=your-template-id
MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/path/to/service-account-key.json
MODEL_ARMOR_TIMEOUT=5.0
MODEL_ARMOR_LOG_VIOLATIONS=true
MODEL_ARMOR_FAIL_OPEN=false
```

### 5. Dependencies
**File**: `pyproject.toml`

Added Google Auth library:
```toml
"google-auth>=2.30.0",
```

Note: Run `uv sync` to install the new dependency.

### 6. Unit Tests
**File**: `tests/unit/test_middleware/test_model_armor_middleware.py`

Comprehensive test suite covering:
- Disabled middleware (no-op behavior)
- Clean content passing sanitization
- User prompt violations blocking requests
- Model response violations blocking responses
- API error handling (fail-open and fail-closed modes)
- Message extraction (string and multimodal content)
- Configuration validation

Run tests with:
```bash
uv run pytest tests/unit/test_middleware/test_model_armor_middleware.py -v
```

### 7. Documentation
**File**: `docs/guides/model-armor.md`

Complete user guide covering:
- Overview and features
- Prerequisites and setup instructions
- Configuration reference
- How it works (request flow, violation handling)
- Performance impact and optimization
- Monitoring and troubleshooting
- Testing procedures (local, unit, integration)
- Deployment guides (staging and production)
- Security considerations
- FAQ

### 8. Project Documentation Updates
**Files**: `CLAUDE.md`

Added Model Armor references:
- Key dependency: google-auth
- ava_v1 features: Model Armor middleware
- Configuration section with link to detailed guide

## Key Features

### Auto-Enable in Production
Model Armor automatically enables when `ENV_MODE=PRODUCTION`:
```python
def _is_model_armor_enabled() -> bool:
    explicit = os.getenv("MODEL_ARMOR_ENABLED", "").lower()
    if explicit in ["true", "false"]:
        return explicit == "true"

    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    return env_mode == "PRODUCTION"
```

### Fail-Fast Configuration Validation
Invalid configuration errors are caught at server startup, not runtime:
```python
class ModelArmorMiddleware(AgentMiddleware):
    def __init__(self):
        # Validate config at startup (fail fast)
        self.config = _get_model_armor_config()
        # Raises ModelArmorConfigError if invalid
```

### Message Scope Optimization
Only checks the last user message per turn (not entire history):
- Reduces API latency (single message vs full conversation)
- Minimizes API costs
- Focuses on new user input

### Safe Error Messages
Generic user-facing errors, detailed logs for debugging:
- User prompt violation: "I'm unable to process that request as it violates our content policy. Please rephrase your question."
- Model response violation: "I apologize, but I cannot provide that information. How else can I assist you with your hotel reservation?"

### Configurable Fail-Open/Fail-Closed
- `MODEL_ARMOR_FAIL_OPEN=false` (default): Block requests if API unavailable (strict enforcement)
- `MODEL_ARMOR_FAIL_OPEN=true`: Allow requests if API unavailable (high availability)

## Architecture

### Middleware Stack Position
Model Armor is the last middleware in the ava_v1 stack:

```python
middleware=[
    SummarizationMiddleware(...),
    ModelFallbackMiddleware(...),
    AnthropicPromptCachingMiddleware(ttl="5m"),
    customize_agent_prompt,
    ForcedRetryMiddleware(),
    ModelArmorMiddleware(),  # Last - processes final user message and model output
]
```

### Request Flow
```
User Message
    ↓
[Model Armor Pre-Call Check]
    ↓ (if clean)
LLM Model (Claude Haiku)
    ↓
[Model Armor Post-Call Check]
    ↓ (if clean)
User Response
```

If either check fails, the request/response is blocked and a safe error is returned.

### API Endpoints Used
- **Pre-call**: `POST /v1/projects/{project}/locations/{location}/templates/{template}:sanitizeUserPrompt`
- **Post-call**: `POST /v1/projects/{project}/locations/{location}/templates/{template}:sanitizeModelResponse`

## Performance Impact

### Expected Latency
- Pre-call check: 100-300ms
- Post-call check: 100-300ms
- Total overhead: 200-600ms per LLM call

### Mitigation Strategies
1. Aggressive 5s timeout (configurable)
2. Fail-open mode for high-availability scenarios
3. Message scope optimization (last message only)
4. Regional deployment close to Model Armor API

## Security Considerations

### Service Account Permissions
Use least-privilege principle:
- Grant only `roles/modelarmor.user`
- Separate service accounts for staging/production
- Rotate keys every 90 days

### Secret Management
- Never commit service account keys to git
- Use environment variables or secret managers (K8s secrets, Railway variables)
- Verify file permissions: `chmod 600 /path/to/key.json`

### Logging Safety
- Violation metadata logged (filter_results), not full content
- User prompts only logged at DEBUG level
- Safe error messages to users (no policy details exposed)

## Testing Strategy

### Unit Tests
Mock-based tests for all core functionality:
- Configuration validation
- Message extraction (string and multimodal)
- Violation handling (user prompt and model response)
- API error handling (fail-open and fail-closed)
- Disabled middleware behavior

### Integration Tests
Verify no breakage of existing functionality:
```bash
uv run pytest  # Full test suite
uv run pytest tests/e2e/test_agent_protocol.py -v  # E2E tests
```

### Local Testing
Manual testing with real Model Armor API:
1. Set up GCP project and service account
2. Configure environment variables
3. Start server and send test requests
4. Monitor logs for `[MODEL_ARMOR]` prefix
5. Test clean content (should pass)
6. Test violating content (should block)

## Deployment Instructions

### Prerequisites
1. GCP project with Model Armor API enabled
2. Model Armor template created and configured
3. Service account with `roles/modelarmor.user` permission
4. Service account key JSON file downloaded

### Staging (Railway)
1. Add environment variables in Railway dashboard
2. Upload service account key as file variable
3. Deploy: `git push origin development`
4. Monitor logs for initialization message

### Production (GKE)
1. Create Kubernetes secret from service account file
2. Update deployment YAML with environment variables
3. Mount secret as volume at service account path
4. Deploy: `kubectl apply -f deployment.yaml`
5. Monitor rollout and check logs

### Rollback
Simply set `MODEL_ARMOR_ENABLED=false` and redeploy. No code changes required.

## Next Steps

### Before First Use
1. **Install dependency**: Run `uv sync` to install google-auth
2. **GCP Setup**: Follow setup guide in `docs/guides/model-armor.md`
3. **Test locally**: Verify configuration with test GCP project
4. **Run tests**: Ensure all unit tests pass
5. **Monitor staging**: Deploy to staging and monitor for 48 hours
6. **Production rollout**: Enable in production with fail-open mode initially

### Monitoring
Watch for these log messages:
- `[MODEL_ARMOR] Middleware enabled` - Successful initialization
- `[MODEL_ARMOR] User prompt blocked` - Policy violation detected
- `[MODEL_ARMOR] Model response blocked` - Model output filtered
- `[MODEL_ARMOR] API timeout` - Model Armor API issues
- `[MODEL_ARMOR] Fail-open mode` - Requests allowed despite API errors

### Fine-Tuning
1. Monitor violation rate in production
2. Analyze violation patterns (categories, scores)
3. Adjust Model Armor template policy in GCP Console
4. Consider fail-open mode for high-availability periods
5. Tune timeout based on observed API latency

## Files Created/Modified

### Created (7 files)
1. `graphs/ava_v1/shared_libraries/model_armor_client.py` - API client
2. `graphs/ava_v1/middleware/model_armor.py` - Middleware class
3. `tests/unit/test_middleware/test_model_armor_middleware.py` - Unit tests
4. `docs/guides/model-armor.md` - User guide
5. `docs/api/model-armor-implementation-summary.md` - This file

### Modified (5 files)
1. `graphs/ava_v1/middleware.py` → `graphs/ava_v1/middleware/__init__.py` - Reorganized
2. `graphs/ava_v1/graph.py` - Added ModelArmorMiddleware to stack
3. `.env.example` - Added 8 environment variables
4. `pyproject.toml` - Added google-auth dependency
5. `CLAUDE.md` - Added Model Armor documentation references

## Verification Checklist

Before deploying to production:

- [ ] Run `uv sync` to install google-auth dependency
- [ ] Run unit tests: `uv run pytest tests/unit/test_middleware/test_model_armor_middleware.py -v`
- [ ] Run full test suite: `uv run pytest`
- [ ] Set up GCP project and Model Armor template
- [ ] Create service account with correct permissions
- [ ] Download service account key JSON file
- [ ] Test locally with real Model Armor API
- [ ] Verify clean content passes sanitization
- [ ] Verify violating content is blocked
- [ ] Test fail-open and fail-closed modes
- [ ] Deploy to staging environment
- [ ] Monitor staging for 48 hours
- [ ] Review violation logs and adjust template if needed
- [ ] Deploy to production with fail-open mode initially
- [ ] Monitor production for 48 hours
- [ ] Switch to fail-closed mode for strict enforcement

## Support and Troubleshooting

For detailed troubleshooting steps, see:
- `docs/guides/model-armor.md` - Complete guide with troubleshooting section
- Logs: Search for `[MODEL_ARMOR]` prefix
- Tests: `tests/unit/test_middleware/test_model_armor_middleware.py`

Common issues:
1. **Configuration errors**: Check environment variables and service account file
2. **Authentication errors**: Verify service account permissions and key validity
3. **API timeouts**: Increase timeout or enable fail-open mode
4. **High violation rate**: Review and adjust Model Armor template policy

## References

- [Google Model Armor Documentation](https://cloud.google.com/model-armor/docs)
- [Model Armor API Reference](https://cloud.google.com/model-armor/docs/reference)
- [Aegra JWT Authentication Guide](./jwt-authentication.md)
- [LangChain Middleware Documentation](https://langchain.readthedocs.io/en/latest/modules/agents/middleware.html)
