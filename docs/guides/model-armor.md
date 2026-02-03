# Google Model Armor Integration

Model Armor is a middleware component that enforces content policy using Google's Model Armor API. It sanitizes both user prompts and model responses to ensure compliance with content policies before and after LLM calls.

## Overview

The Model Armor middleware intercepts every LLM call in the ava_v1 graph to:

1. **Pre-call sanitization**: Check user prompts against Google's content policy before sending to the model
2. **Post-call sanitization**: Check model responses against content policy before returning to the user

If content violates policy at either stage, the middleware blocks the request/response and returns a safe, generic error message.

## Features

- Automatic policy enforcement for all ava_v1 conversations
- Configurable fail-open/fail-closed modes for API unavailability
- Auto-enable in production environments
- Detailed violation logging for analysis
- Low-latency checks with configurable timeouts (5s default)
- Service account-based authentication with automatic token refresh

## Prerequisites

1. **GCP Account**: Active Google Cloud Platform account
2. **Model Armor API**: Enabled in your GCP project
3. **Model Armor Template**: Created and configured in GCP Console
4. **Service Account**: With Model Armor API permissions

### Step 1: Enable Model Armor API

```bash
# Enable the API in your GCP project
gcloud services enable modelarmor.googleapis.com --project=YOUR_PROJECT_ID
```

### Step 2: Create Model Armor Template

1. Navigate to [Model Armor Console](https://console.cloud.google.com/ai/model-armor)
2. Click "Create Template"
3. Configure policy rules:
   - Hate speech detection
   - Harmful content filtering
   - PII detection (optional)
   - Custom rules (optional)
4. Name your template (e.g., `aegra-production`)
5. Note the Template ID for configuration

### Step 3: Create Service Account

```bash
# Create service account
gcloud iam service-accounts create model-armor-sa \
  --display-name="Model Armor Service Account" \
  --project=YOUR_PROJECT_ID

# Grant Model Armor API permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"

# Generate and download key file
gcloud iam service-accounts keys create model-armor-key.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Move key file to secure location
mv model-armor-key.json /path/to/secure/location/
chmod 600 /path/to/secure/location/model-armor-key.json
```

### Step 4: Configure Environment Variables

Add the following to your `.env` file:

```bash
# Google Model Armor Configuration
MODEL_ARMOR_ENABLED=true  # Or omit to auto-enable in production
MODEL_ARMOR_PROJECT_ID=your-gcp-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-production
MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/path/to/secure/location/model-armor-key.json
MODEL_ARMOR_TIMEOUT=5.0
MODEL_ARMOR_LOG_VIOLATIONS=true
MODEL_ARMOR_FAIL_OPEN=false
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_ARMOR_ENABLED` | No | Auto (true in PRODUCTION) | Explicitly enable/disable middleware |
| `MODEL_ARMOR_PROJECT_ID` | Yes* | - | GCP project ID where Model Armor is enabled |
| `MODEL_ARMOR_LOCATION` | Yes* | - | GCP region (e.g., us-central1, europe-west1) |
| `MODEL_ARMOR_TEMPLATE_ID` | Yes* | - | Model Armor template name/ID |
| `MODEL_ARMOR_SERVICE_ACCOUNT_PATH` | Yes* | - | Path to service account JSON key file |
| `MODEL_ARMOR_TIMEOUT` | No | 5.0 | API timeout in seconds (max 30) |
| `MODEL_ARMOR_LOG_VIOLATIONS` | No | true | Log detailed violation information |
| `MODEL_ARMOR_FAIL_OPEN` | No | false | Allow requests if API unavailable |

*Required when `MODEL_ARMOR_ENABLED=true` or `ENV_MODE=PRODUCTION`

### Auto-Enable Behavior

Model Armor automatically enables in production environments:

```python
# Explicitly disabled
MODEL_ARMOR_ENABLED=false  # Disabled (overrides ENV_MODE)

# Explicitly enabled
MODEL_ARMOR_ENABLED=true   # Enabled (requires full config)

# Auto-enable in production
ENV_MODE=PRODUCTION        # Enabled (requires full config)

# Disabled by default in local/development
ENV_MODE=LOCAL             # Disabled (unless explicitly enabled)
ENV_MODE=DEVELOPMENT       # Disabled (unless explicitly enabled)
```

### Fail Open vs Fail Closed

The `MODEL_ARMOR_FAIL_OPEN` setting controls behavior when the Model Armor API is unavailable:

**Fail Closed (default, `MODEL_ARMOR_FAIL_OPEN=false`)**:
- Blocks all requests if API is unreachable
- Ensures 100% policy enforcement
- Returns error to user: "Content policy service unavailable"
- Use for: High-security environments, strict compliance requirements

**Fail Open (`MODEL_ARMOR_FAIL_OPEN=true`)**:
- Allows requests to proceed if API is unreachable
- Logs error but doesn't block user
- Reduces impact of API outages on availability
- Use for: High-availability requirements, graceful degradation

## How It Works

### Request Flow

```
User Message
    ↓
[Model Armor Pre-Call Check]
    ↓ (if clean)
LLM Model Call
    ↓
[Model Armor Post-Call Check]
    ↓ (if clean)
User Response
```

### Violation Handling

**User Prompt Violation**:
- User submits: "inappropriate content example"
- Model Armor blocks request
- User receives: "I'm unable to process that request as it violates our content policy. Please rephrase your question."
- Model is never called

**Model Response Violation**:
- Model generates: "inappropriate response example"
- Model Armor blocks response
- User receives: "I apologize, but I cannot provide that information. How else can I assist you with your hotel reservation?"
- Original response is discarded

### Message Scope

The middleware checks only the **last user message** in each turn, not the entire conversation history. This approach:

- Reduces API latency (single message vs full history)
- Minimizes API costs
- Focuses on new user input per turn
- Maintains conversation context without redundant checks

## Performance Impact

Model Armor adds latency to each LLM call:

- **Pre-call check**: 100-300ms (1 API call)
- **Post-call check**: 100-300ms (1 API call)
- **Total overhead**: 200-600ms per model call

### Optimization Strategies

1. **Aggressive timeout**: Default 5s timeout prevents long waits
2. **Fail-open mode**: Enable for high-availability use cases
3. **Regional deployment**: Deploy close to Model Armor API endpoints
4. **Caching**: Model Armor API may cache similar content checks

## Monitoring and Troubleshooting

### Log Levels

Model Armor uses structured logging with the `[MODEL_ARMOR]` prefix:

**INFO**: Initialization and configuration
```
[MODEL_ARMOR] Middleware enabled (project=my-project, location=us-central1, template=prod-template, timeout=5.0s, fail_open=false)
[MODEL_ARMOR] Middleware disabled
```

**DEBUG**: Sanitization operations
```
[MODEL_ARMOR] Sanitizing user prompt (length=42)
[MODEL_ARMOR] User prompt passed sanitization
[MODEL_ARMOR] Sanitizing model response (length=156)
[MODEL_ARMOR] Model response passed sanitization
```

**WARNING**: Policy violations
```
[MODEL_ARMOR] User prompt blocked: {'blocked': True, 'reason': 'inappropriate_content', 'categories': ['hate_speech']}
[MODEL_ARMOR] Model response blocked: {'blocked': True, 'reason': 'policy_violation'}
[MODEL_ARMOR] Fail-open mode: allowing request despite timeout
```

**ERROR**: API errors
```
[MODEL_ARMOR] Model Armor API timeout after 5.0s: TimeoutException
[MODEL_ARMOR] Model Armor API error (status 503): Service Unavailable
[MODEL_ARMOR] Failed to generate access token: InvalidServiceAccountError
```

### Common Issues

#### 1. Configuration Errors (Startup Failures)

**Symptom**: Server fails to start with `ModelArmorConfigError`

**Causes**:
- Missing required environment variables
- Service account file not found
- Invalid service account credentials
- Invalid timeout value (>30s or ≤0s)

**Solution**:
```bash
# Verify all required variables are set
env | grep MODEL_ARMOR

# Check service account file exists and is readable
ls -l /path/to/service-account-key.json
cat /path/to/service-account-key.json | jq .

# Verify file permissions (should be 600 or 400)
chmod 600 /path/to/service-account-key.json

# Test service account credentials
gcloud auth activate-service-account --key-file=/path/to/service-account-key.json
```

#### 2. Authentication Errors

**Symptom**: `Failed to generate access token` in logs

**Causes**:
- Invalid service account JSON file
- Service account lacks Model Armor permissions
- Service account deleted or disabled

**Solution**:
```bash
# Verify service account exists
gcloud iam service-accounts describe model-armor-sa@PROJECT_ID.iam.gserviceaccount.com

# Check IAM permissions
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:model-armor-sa@PROJECT_ID.iam.gserviceaccount.com"

# Re-grant permissions if missing
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:model-armor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"
```

#### 3. API Timeouts

**Symptom**: `Model Armor API timeout after 5.0s` in logs

**Causes**:
- Network latency to GCP
- Model Armor API overloaded
- Timeout setting too aggressive

**Solution**:
```bash
# Increase timeout (up to 30s max)
MODEL_ARMOR_TIMEOUT=10.0

# Enable fail-open mode for high availability
MODEL_ARMOR_FAIL_OPEN=true

# Test network connectivity to Model Armor API
curl -I https://modelarmor.us-central1.rep.googleapis.com

# Check GCP status page
open https://status.cloud.google.com
```

#### 4. High Violation Rate

**Symptom**: Many blocked requests in logs

**Causes**:
- Template policy too strict
- Legitimate content triggering false positives
- User testing with violation examples

**Solution**:
```bash
# Review violation logs for patterns
grep "\[MODEL_ARMOR\] User prompt blocked" logs/aegra.log | jq .filter_results

# Adjust template policy in GCP Console
# - Review category thresholds (LOW, MEDIUM, HIGH)
# - Add allowlist rules for specific patterns
# - Test changes in staging environment

# Consider fail-open mode during template tuning
MODEL_ARMOR_FAIL_OPEN=true
```

### Analyzing Violations

When `MODEL_ARMOR_LOG_VIOLATIONS=true`, detailed violation data is logged:

```python
{
  "blocked": true,
  "reason": "inappropriate_content",
  "categories": ["hate_speech", "violence"],
  "scores": {
    "hate_speech": 0.95,
    "violence": 0.72,
    "sexual": 0.12
  },
  "filtered_text_ranges": [[0, 50]]
}
```

Use this data to:
- Identify common violation patterns
- Fine-tune template policies
- Train users on policy guidelines
- Debug false positives

## Testing

### Local Testing

1. Set up test environment variables:
```bash
export MODEL_ARMOR_ENABLED=true
export MODEL_ARMOR_PROJECT_ID=test-project
export MODEL_ARMOR_LOCATION=us-central1
export MODEL_ARMOR_TEMPLATE_ID=test-template
export MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/path/to/test-key.json
```

2. Start the server:
```bash
uv run uvicorn src.agent_server.main:app --reload
```

3. Send test request (clean content):
```bash
# Generate JWT token
TOKEN=$(uv run python scripts/generate_jwt_token.py --sub test-user)

# Create thread
THREAD_ID=$(curl -s -X POST http://localhost:8000/assistants/ava_v1/threads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  | jq -r .thread_id)

# Send clean message
curl -X POST http://localhost:8000/threads/$THREAD_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Book me a hotel in Miami"}'

# Check logs
tail -f logs/aegra.log | grep MODEL_ARMOR
# Should see: "User prompt passed", "Model response passed"
```

4. Test violation (use content that violates your template policy):
```bash
# Send violating message
curl -X POST http://localhost:8000/threads/$THREAD_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "<your-test-violation-content>"}'

# Should receive policy error response
# Should see in logs: "User prompt blocked"
```

### Unit Tests

Run the test suite:

```bash
# Run Model Armor middleware tests
uv run pytest tests/unit/test_middleware/test_model_armor_middleware.py -v

# Run with coverage
uv run pytest tests/unit/test_middleware/test_model_armor_middleware.py \
  --cov=graphs/ava_v1/middleware/model_armor \
  --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Integration Tests

Verify Model Armor doesn't break existing functionality:

```bash
# Run full test suite
uv run pytest

# Run E2E tests specifically
uv run pytest tests/e2e/test_agent_protocol.py -v
```

## Deployment

### Staging (Railway)

1. Add service account credentials to Railway secrets:
```bash
# In Railway dashboard:
# 1. Go to your project
# 2. Click on "Variables" tab
# 3. Add the following variables:

MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=staging-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=staging-template
MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/app/model-armor-key.json
MODEL_ARMOR_TIMEOUT=5.0
MODEL_ARMOR_LOG_VIOLATIONS=true
MODEL_ARMOR_FAIL_OPEN=false

# 4. Add service account JSON as file:
#    - Click "Add file"
#    - Name: model-armor-key.json
#    - Paste JSON contents
```

2. Deploy:
```bash
git push origin development  # Auto-deploys to Railway
```

3. Monitor logs:
```bash
# In Railway dashboard, check deployment logs for:
[MODEL_ARMOR] Middleware enabled (project=staging-project-id, ...)
```

### Production (GKE)

1. Create Kubernetes secret:
```bash
# Create secret from service account file
kubectl create secret generic model-armor-sa \
  --from-file=key.json=/path/to/production-key.json \
  --namespace=aegra-prod

# Verify secret
kubectl get secret model-armor-sa -n aegra-prod -o yaml
```

2. Update deployment YAML:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegra
  namespace: aegra-prod
spec:
  template:
    spec:
      containers:
      - name: aegra
        env:
        - name: MODEL_ARMOR_ENABLED
          value: "true"  # Or omit to auto-enable
        - name: MODEL_ARMOR_PROJECT_ID
          value: "production-project-id"
        - name: MODEL_ARMOR_LOCATION
          value: "us-central1"
        - name: MODEL_ARMOR_TEMPLATE_ID
          value: "production-template"
        - name: MODEL_ARMOR_SERVICE_ACCOUNT_PATH
          value: "/etc/model-armor/key.json"
        - name: MODEL_ARMOR_TIMEOUT
          value: "5.0"
        - name: MODEL_ARMOR_LOG_VIOLATIONS
          value: "true"
        - name: MODEL_ARMOR_FAIL_OPEN
          value: "false"
        volumeMounts:
        - name: model-armor-sa
          mountPath: /etc/model-armor
          readOnly: true
      volumes:
      - name: model-armor-sa
        secret:
          secretName: model-armor-sa
```

3. Deploy:
```bash
kubectl apply -f deployments/k8s/deployment.yaml
```

4. Monitor rollout:
```bash
# Watch pod status
kubectl rollout status deployment/aegra -n aegra-prod

# Check logs for Model Armor initialization
kubectl logs -f deployment/aegra -n aegra-prod | grep MODEL_ARMOR
```

### Rollback

To disable Model Armor without code changes:

**Railway**:
```bash
# Set variable in Railway dashboard
MODEL_ARMOR_ENABLED=false
```

**GKE**:
```bash
# Update deployment
kubectl set env deployment/aegra MODEL_ARMOR_ENABLED=false -n aegra-prod

# Or edit YAML and reapply
kubectl edit deployment aegra -n aegra-prod
```

## Security Considerations

1. **Service Account Permissions**: Use least-privilege principle
   - Grant only `roles/modelarmor.user` role
   - Do not grant `roles/owner` or broad permissions
   - Use separate service accounts for staging/production

2. **Secret Management**: Never commit credentials
   - Add `*-key.json` to `.gitignore`
   - Use environment variables or secret managers
   - Rotate service account keys periodically (90 days)
   - Audit service account usage regularly

3. **Logging Safety**: Sanitize sensitive data
   - Middleware logs violation metadata, not full content
   - User prompts only logged at DEBUG level (disabled in production)
   - Filter logs before sharing externally

4. **Error Messages**: Don't expose policy details
   - Generic error messages to users
   - Detailed violations only in server logs
   - No raw API responses in user-facing errors

5. **Network Security**:
   - API calls use HTTPS (TLS 1.2+)
   - Service account tokens expire after 1 hour
   - Tokens regenerated per request (no caching)

## FAQ

### Q: Does Model Armor check the entire conversation history?

**A**: No, it only checks the last user message per turn. This reduces latency and cost while focusing on new user input.

### Q: What happens if the Model Armor API is down?

**A**: Depends on `MODEL_ARMOR_FAIL_OPEN`:
- `false` (default): Requests are blocked, user sees error
- `true`: Requests proceed, error is logged

### Q: Can I use Model Armor in local development?

**A**: Yes, but you need a GCP project with Model Armor enabled and a service account. For local testing, consider using a sandbox GCP project with a test template.

### Q: Does Model Armor work with other graphs besides ava_v1?

**A**: Currently, it's only integrated with ava_v1. To add to other graphs, include `ModelArmorMiddleware()` in their middleware list.

### Q: How much does Model Armor cost?

**A**: See [Model Armor Pricing](https://cloud.google.com/model-armor/pricing). Costs scale with API call volume. Typical usage: 2 API calls per LLM interaction (pre-call + post-call).

### Q: Can I customize the error messages?

**A**: Yes, edit the violation response messages in `graphs/ava_v1/middleware/model_armor.py`:
- User prompt violation: Line ~155
- Model response violation: Line ~185

### Q: How do I test without triggering real violations?

**A**: Create a test Model Armor template with strict policies, then use test content that you know violates those policies. Monitor logs to verify blocks.

### Q: Can I disable Model Armor for specific users or conversations?

**A**: Not currently supported. Model Armor applies to all ava_v1 conversations when enabled. To add per-user controls, modify the middleware to check user metadata before sanitizing.

## Additional Resources

- [Google Model Armor Documentation](https://cloud.google.com/model-armor/docs)
- [Model Armor API Reference](https://cloud.google.com/model-armor/docs/reference)
- [GCP Service Accounts Guide](https://cloud.google.com/iam/docs/service-accounts)
- [Aegra Authentication Guide](./jwt-authentication.md)
