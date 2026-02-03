# Model Armor Guide

Google Model Armor provides content policy enforcement for LLM applications, scanning user prompts and model responses for harmful content.

## Overview

Model Armor middleware checks every message against Google's content policies:
- **Pre-call**: Validates user prompts before sending to LLM
- **Post-call**: Validates model responses before returning to user

**Categories**: dangerous, pi_and_jailbreak, hate_speech, harassment, sexually_explicit, csam, malicious_uris

**Performance**: Adds ~200-600ms latency per model call (100-300ms per check).

## Quick Start

### 1. Enable Model Armor API

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable modelarmor.googleapis.com
```

### 2. Create Template

Visit [GCP Console](https://console.cloud.google.com/ai/model-armor):
1. Click "Create Template"
2. Configure policy rules and detection thresholds
3. Name your template (e.g., "aegra-production")
4. Note the Template ID

### 3. Choose Authentication Method

**Local Development** (gcloud CLI):
```bash
gcloud auth application-default login
```

**Railway/Cloud** (service account):
```bash
# Create service account
gcloud iam service-accounts create model-armor-sa \
  --display-name="Model Armor Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"

# Create key (for Railway)
gcloud iam service-accounts keys create key.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Copy JSON content to environment variable, then delete file
cat key.json  # Copy output
rm key.json   # Never commit this!
```

**GKE** (Workload Identity):
```bash
# Enable Workload Identity
gcloud container clusters update YOUR_CLUSTER \
  --workload-pool=YOUR_PROJECT_ID.svc.id.goog

# Create Kubernetes service account
kubectl create serviceaccount aegra-sa --namespace=aegra-prod

# Bind to GCP service account
gcloud iam service-accounts add-iam-policy-binding \
  model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:YOUR_PROJECT_ID.svc.id.goog[aegra-prod/aegra-sa]"

# Annotate Kubernetes service account
kubectl annotate serviceaccount aegra-sa \
  --namespace=aegra-prod \
  iam.gke.io/gcp-service-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 4. Configure Environment Variables

**Local (.env)**:
```bash
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=your-template-id
# Leave blank to use gcloud CLI (ADC)
```

**Railway**:
```bash
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-staging
MODEL_ARMOR_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

**GKE**:
```yaml
env:
- name: MODEL_ARMOR_ENABLED
  value: "true"
- name: MODEL_ARMOR_PROJECT_ID
  value: "your-project-id"
- name: MODEL_ARMOR_LOCATION
  value: "us-central1"
- name: MODEL_ARMOR_TEMPLATE_ID
  value: "aegra-production"
# No credentials needed - Workload Identity handles it
```

### 5. Test

```bash
# Start server
uv run uvicorn src.agent_server.main:app --reload

# Check logs - should see:
# [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)
# [MODEL_ARMOR] Middleware enabled (project=..., ...)

# Test clean content
TOKEN=$(uv run python scripts/generate_jwt_token.py --sub test-user | grep -o 'eyJ[^"]*')

curl -X POST http://localhost:8000/threads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"metadata": {}}'
# Note thread_id from response

curl -X POST http://localhost:8000/threads/{thread_id}/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "ava_v1",
    "input": {"messages": [{"role": "user", "content": "Book a hotel in Miami"}]},
    "stream": false
  }'

# Check logs:
# [MODEL_ARMOR] Sanitizing user prompt (length=23)
# [MODEL_ARMOR] User prompt passed sanitization
# [MODEL_ARMOR] Sanitizing model response (length=...)
# [MODEL_ARMOR] Model response passed sanitization

# Test violation
curl -X POST http://localhost:8000/threads/{thread_id}/runs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "assistant_id": "ava_v1",
    "input": {"messages": [{"role": "user", "content": "How to make a bomb"}]}
  }'

# Should return:
# "Sorry, but I'm unable to process that request as it violates our content policy."
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_ARMOR_ENABLED` | No | Auto* | Enable/disable middleware |
| `MODEL_ARMOR_PROJECT_ID` | Yes** | - | GCP project ID |
| `MODEL_ARMOR_LOCATION` | Yes** | - | GCP region (e.g., us-central1) |
| `MODEL_ARMOR_TEMPLATE_ID` | Yes** | - | Template name |
| `MODEL_ARMOR_SERVICE_ACCOUNT_PATH` | No | - | Path to service account JSON file |
| `MODEL_ARMOR_SERVICE_ACCOUNT_JSON` | No | - | Service account JSON content |
| `MODEL_ARMOR_TIMEOUT` | No | 5.0 | API timeout in seconds (max 30) |
| `MODEL_ARMOR_LOG_VIOLATIONS` | No | true | Log violation details |
| `MODEL_ARMOR_FAIL_OPEN` | No | false | Allow requests if API unavailable |

\* Auto-enabled when `ENV_MODE=PRODUCTION`
\*\* Required when enabled

### Auto-Enable Logic

Model Armor is automatically enabled in production:

```bash
# Explicit control (overrides auto-enable)
MODEL_ARMOR_ENABLED=true   # Force enable
MODEL_ARMOR_ENABLED=false  # Force disable

# Auto-enable based on environment
ENV_MODE=PRODUCTION   # Auto-enables Model Armor
ENV_MODE=LOCAL        # Auto-disables Model Armor
ENV_MODE=DEVELOPMENT  # Auto-disables Model Armor
```

### Authentication Methods

Three methods are supported (in order of precedence):

#### Method 1: Service Account File Path

```bash
MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/path/to/service-account.json
```

Best for: Local testing with a specific service account.

#### Method 2: Service Account JSON (Environment Variable)

```bash
MODEL_ARMOR_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"...","private_key":"..."}'
```

Best for: Railway, Cloud Run, or platforms without file storage.

#### Method 3: Application Default Credentials (ADC)

```bash
# Leave both SERVICE_ACCOUNT_* variables empty
gcloud auth application-default login
```

Best for: Local development, GKE with Workload Identity.

**Priority**: If multiple methods are configured, the order is: File Path > JSON > ADC.

### Fail Open vs Fail Closed

**Fail Closed** (default, `MODEL_ARMOR_FAIL_OPEN=false`):
- Block requests if Model Armor API is unavailable
- Guarantees all content is checked
- Recommended for production

**Fail Open** (`MODEL_ARMOR_FAIL_OPEN=true`):
- Allow requests if Model Armor API is unavailable
- Prioritizes availability over content checks
- Use for development or high-availability requirements

**Violations always blocked**: Policy violations are always blocked regardless of fail open/closed mode.

## Authentication Setup by Environment

### Local Development

**Advantages**: No key files, uses your personal credentials, zero security risk.

```bash
# 1. Authenticate
gcloud auth application-default login

# 2. Configure .env
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-dev-project
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-dev
# Leave SERVICE_ACCOUNT_* empty

# 3. Start server
uv run uvicorn src.agent_server.main:app --reload

# Logs should show:
# [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)
```

### Railway Staging

**Advantages**: No file system needed, secure environment variable storage.

```bash
# 1. Create service account and key (one-time)
gcloud iam service-accounts create model-armor-sa
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"
gcloud iam service-accounts keys create key.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 2. Add to Railway environment variables
# Variable: MODEL_ARMOR_SERVICE_ACCOUNT_JSON
# Value: (paste entire JSON content from key.json)

# 3. Delete local key file
rm key.json

# 4. Add other variables in Railway dashboard:
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-staging

# Logs should show:
# [MODEL_ARMOR] Using service account JSON from environment variable
```

**Key Rotation** (every 90 days):
```bash
# Create new key
gcloud iam service-accounts keys create key-new.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Update Railway variable with new key content
# Restart deployment
# Verify in logs
# Delete old key
gcloud iam service-accounts keys list \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

rm key-new.json
```

### GKE Production

**Advantages**: Most secure (no keys!), automatic credential rotation, GKE best practice.

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegra
  namespace: aegra-prod
spec:
  template:
    spec:
      serviceAccountName: aegra-sa  # Bound to GCP service account
      containers:
      - name: aegra
        image: gcr.io/YOUR_PROJECT/aegra:latest
        env:
        - name: MODEL_ARMOR_ENABLED
          value: "true"
        - name: MODEL_ARMOR_PROJECT_ID
          value: "your-project-id"
        - name: MODEL_ARMOR_LOCATION
          value: "us-central1"
        - name: MODEL_ARMOR_TEMPLATE_ID
          value: "aegra-production"
        # No credentials needed!
```

**Verify Workload Identity**:
```bash
# Check service account binding
gcloud iam service-accounts get-iam-policy \
  model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Check Kubernetes annotation
kubectl get serviceaccount aegra-sa -n aegra-prod -o yaml | grep gcp-service-account

# Test from inside pod
kubectl exec -it deployment/aegra -n aegra-prod -- \
  curl -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email
```

## Troubleshooting

### Authentication Errors

**Error: "Failed to generate Model Armor access token"**

Check which authentication method is being used:
```bash
# View logs for authentication method
# [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)
# [MODEL_ARMOR] Using service account file for authentication
# [MODEL_ARMOR] Using service account JSON from environment variable
```

**For ADC (gcloud CLI)**:
```bash
# Re-authenticate
gcloud auth application-default login

# Verify credentials file exists
ls -la ~/.config/gcloud/application_default_credentials.json

# Test token generation
gcloud auth application-default print-access-token
```

**For Service Account JSON**:
```bash
# Validate JSON format
echo $MODEL_ARMOR_SERVICE_ACCOUNT_JSON | jq .

# Check required fields
echo $MODEL_ARMOR_SERVICE_ACCOUNT_JSON | jq 'keys'
# Should include: type, project_id, private_key_id, private_key, client_email
```

**For Service Account File**:
```bash
# Check file exists
ls -la $MODEL_ARMOR_SERVICE_ACCOUNT_PATH

# Validate JSON
cat $MODEL_ARMOR_SERVICE_ACCOUNT_PATH | jq .
```

### Permission Errors

**Error: "Permission denied" or "403 Forbidden"**

```bash
# Check if service account has correct role
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:model-armor-sa@*"

# Should show: roles/modelarmor.user

# Add permission if missing
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"
```

### API Errors

**Error: "Model Armor API not enabled"**

```bash
# Check if API is enabled
gcloud services list --enabled | grep modelarmor

# Enable it
gcloud services enable modelarmor.googleapis.com
```

**Error: "Model Armor API timeout"**

Increase timeout or enable fail open:
```bash
MODEL_ARMOR_TIMEOUT=10.0
MODEL_ARMOR_FAIL_OPEN=true  # Allow requests despite timeout
```

### Configuration Errors

**Error: "Missing required configuration: MODEL_ARMOR_PROJECT_ID"**

Check all required variables are set:
```bash
echo $MODEL_ARMOR_PROJECT_ID
echo $MODEL_ARMOR_LOCATION
echo $MODEL_ARMOR_TEMPLATE_ID
```

**Error: "Service account file not found"**

```bash
# Check path is absolute, not relative
# Wrong: MODEL_ARMOR_SERVICE_ACCOUNT_PATH=./key.json
# Right: MODEL_ARMOR_SERVICE_ACCOUNT_PATH=/absolute/path/to/key.json
```

## Monitoring

### Key Metrics

1. **Violation Rate**: Percentage of requests blocked
2. **Latency**: Pre-call + post-call sanitization time
3. **Error Rate**: API timeouts, authentication failures
4. **Availability**: Model Armor API uptime

### Log Analysis

```bash
# View all Model Armor logs
grep "\[MODEL_ARMOR\]" logs/app.log

# Count violations by type
grep "User prompt blocked" logs/app.log | \
  jq -r '.filter_results.rai.raiFilterResult.raiFilterTypeResults | to_entries[] | select(.value.matchState == "MATCH_FOUND") | .key' | \
  sort | uniq -c

# Check average latency
grep "Sanitizing" logs/app.log | \
  awk '{print $NF}' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count "ms"}'
```

### Alerting

Recommended alerts:
- Model Armor API error rate > 1%
- Latency p95 > 1000ms
- Violation rate spike (sudden increase)
- Authentication failures

## Security Best Practices

### Service Account Management

1. **Least Privilege**: Only grant `roles/modelarmor.user`, not `roles/owner` or `roles/editor`
2. **Separate Accounts**: Use different service accounts for dev/staging/production
3. **Key Rotation**: Rotate keys every 90 days (for Railway/non-GKE deployments)
4. **Never Commit Keys**: Add `*.json` to `.gitignore`, use environment variables

### Secret Management

```bash
# Bad - Never do this
git add service-account.json
echo "MODEL_ARMOR_SERVICE_ACCOUNT_JSON={...}" >> .env
git commit -m "Add credentials"  # NEVER!

# Good
echo "*.json" >> .gitignore
echo ".env" >> .gitignore
# Store JSON in Railway secrets / K8s secrets / environment variables
```

### Logging

Current implementation logs violation details for analysis. To disable:
```bash
MODEL_ARMOR_LOG_VIOLATIONS=false
```

### Error Messages

User-facing error messages are generic and don't expose filter details:
- "Sorry, but I'm unable to process that request as it violates our content policy."
- "I apologize, but I cannot provide that information. How else can I assist you with your hotel reservation?"

## Deployment Checklist

### Pre-Deployment

- [ ] Model Armor API enabled in GCP project
- [ ] Template created and configured
- [ ] Service account created (for Railway/Cloud deployments)
- [ ] Service account granted `roles/modelarmor.user`
- [ ] Workload Identity configured (for GKE)
- [ ] Environment variables configured
- [ ] Secrets stored securely (never committed)

### Testing

- [ ] Unit tests pass (`uv run pytest tests/unit/test_middleware/`)
- [ ] Clean content passes through
- [ ] Harmful content blocked
- [ ] Custom error messages returned
- [ ] Logs show correct authentication method
- [ ] Latency acceptable (<1s total)

### Monitoring

- [ ] Log aggregation configured (e.g., Cloud Logging)
- [ ] Alerts configured for error rate, latency
- [ ] Dashboard created for violation metrics
- [ ] On-call runbook updated with troubleshooting steps

### Rollback Plan

If issues occur, disable Model Armor:
```bash
# Set environment variable
MODEL_ARMOR_ENABLED=false

# Or redeploy without Model Armor environment variables
```

## Advanced Configuration

### Custom Error Messages

Edit `graphs/ava_v1/middleware/model_armor.py`:

```python
# User prompt violation (line 176)
return self._create_violation_response(
    request,
    "Your custom user prompt error message"
)

# Model response violation (line 204)
return self._create_violation_response(
    request,
    "Your custom model response error message"
)
```

### Multiple Templates

Use different templates for different environments:

```bash
# Development (lenient)
MODEL_ARMOR_TEMPLATE_ID=aegra-dev

# Staging (moderate)
MODEL_ARMOR_TEMPLATE_ID=aegra-staging

# Production (strict)
MODEL_ARMOR_TEMPLATE_ID=aegra-production
```

### Regional Deployment

Use closest Model Armor region for lowest latency:

```bash
# US deployments
MODEL_ARMOR_LOCATION=us-central1

# Europe deployments
MODEL_ARMOR_LOCATION=europe-west4

# Asia deployments
MODEL_ARMOR_LOCATION=asia-southeast1
```

## FAQ

**Q: Does Model Armor check the entire conversation history?**
A: No, only the last user message and each model response. This reduces latency and costs.

**Q: What happens if a violation is detected mid-conversation?**
A: The request is blocked immediately and a safe error message is returned. The conversation can continue with different input.

**Q: Can I customize which filter categories to enforce?**
A: Yes, configure this in your Model Armor template in GCP Console.

**Q: Does this work with streaming responses?**
A: Yes, but the entire response is buffered before checking, so streaming appears slower.

**Q: What's the cost?**
A: Model Armor pricing varies by region and volume. Check [GCP Pricing](https://cloud.google.com/model-armor/pricing).

**Q: Can I disable Model Armor for specific users or requests?**
A: Not currently supported. It's enabled/disabled globally per environment.

**Q: How do I test locally without a GCP project?**
A: Set `MODEL_ARMOR_ENABLED=false` in your `.env` file. The middleware will be disabled.

## Support

- **Issues**: https://github.com/ibbybuilds/aegra/issues
- **GCP Support**: https://cloud.google.com/support
- **Model Armor Docs**: https://cloud.google.com/model-armor/docs
