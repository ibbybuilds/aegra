# Model Armor Authentication Guide

This guide covers all three authentication methods for Model Armor, with a focus on secure, keyless approaches.

## Quick Setup with gcloud CLI

### Prerequisites
- gcloud CLI installed and configured
- Access to a GCP project
- Model Armor API enabled

### Step 1: Enable Model Armor API

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable the API
gcloud services enable modelarmor.googleapis.com
```

### Step 2: Create Model Armor Template

```bash
# Option A: Via GCP Console (recommended for first-time setup)
open "https://console.cloud.google.com/ai/model-armor?project=$(gcloud config get-value project)"

# Follow the UI to:
# 1. Click "Create Template"
# 2. Configure policy rules (hate speech, harmful content, PII, etc.)
# 3. Set detection thresholds (LOW, MEDIUM, HIGH)
# 4. Name your template (e.g., "aegra-production")
# 5. Note the Template ID

# Option B: Via gcloud CLI (if available in your region)
gcloud model-armor templates create aegra-production \
  --location=us-central1 \
  --config=model-armor-config.yaml
```

## Authentication Methods

### Method 1: Application Default Credentials (ADC) - LOCAL DEVELOPMENT

**Best for**: Local development with gcloud CLI

**Advantages**:
- No key files to manage
- Uses your personal gcloud credentials
- Zero security risk (no keys committed)
- Works immediately if gcloud is configured

**Setup**:

```bash
# Authenticate with your Google account
gcloud auth application-default login

# Verify authentication
gcloud auth application-default print-access-token
```

**Configuration (.env)**:

```bash
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-dev

# Leave these empty to use ADC
# MODEL_ARMOR_SERVICE_ACCOUNT_PATH=
# MODEL_ARMOR_SERVICE_ACCOUNT_JSON=
```

**Test it**:

```bash
# Start the server
uv run uvicorn src.agent_server.main:app --reload

# Check logs - should see:
# [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)
# [MODEL_ARMOR] Middleware enabled (project=your-project-id, ...)
```

### Method 2: Workload Identity - GKE PRODUCTION

**Best for**: GKE production deployments

**Advantages**:
- Most secure (no keys at all!)
- Native Kubernetes service account binding
- Automatic credential rotation
- Best practice for GKE

**Setup**:

```bash
# 1. Create GCP service account
gcloud iam service-accounts create model-armor-sa \
  --display-name="Model Armor Service Account" \
  --project=YOUR_PROJECT_ID

# 2. Grant Model Armor permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"

# 3. Enable Workload Identity on your GKE cluster (if not already enabled)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --workload-pool=YOUR_PROJECT_ID.svc.id.goog \
  --region=YOUR_REGION

# 4. Create Kubernetes service account
kubectl create serviceaccount aegra-sa --namespace=aegra-prod

# 5. Bind Kubernetes SA to GCP SA
gcloud iam service-accounts add-iam-policy-binding \
  model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:YOUR_PROJECT_ID.svc.id.goog[aegra-prod/aegra-sa]"

# 6. Annotate Kubernetes service account
kubectl annotate serviceaccount aegra-sa \
  --namespace=aegra-prod \
  iam.gke.io/gcp-service-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

**Deployment YAML**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegra
  namespace: aegra-prod
spec:
  template:
    spec:
      serviceAccountName: aegra-sa  # Use Workload Identity SA
      containers:
      - name: aegra
        image: gcr.io/YOUR_PROJECT/aegra:latest
        env:
        - name: MODEL_ARMOR_ENABLED
          value: "true"
        - name: MODEL_ARMOR_PROJECT_ID
          value: "YOUR_PROJECT_ID"
        - name: MODEL_ARMOR_LOCATION
          value: "us-central1"
        - name: MODEL_ARMOR_TEMPLATE_ID
          value: "aegra-production"
        # No credentials needed - Workload Identity handles it!
```

**Verification**:

```bash
# Deploy and check logs
kubectl logs -f deployment/aegra -n aegra-prod | grep MODEL_ARMOR

# Should see:
# [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)
# [MODEL_ARMOR] Middleware enabled (project=your-project-id, ...)
```

### Method 3: Environment Variable JSON - RAILWAY STAGING

**Best for**: Railway, Cloud Run, or other platforms without Workload Identity

**Advantages**:
- No file system storage needed
- Works on any platform
- Secure (stored as encrypted environment variable)
- Never committed to git

**Setup**:

```bash
# 1. Create service account (if not already created)
gcloud iam service-accounts create model-armor-sa \
  --display-name="Model Armor Service Account" \
  --project=YOUR_PROJECT_ID

# 2. Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"

# 3. Create and download key
gcloud iam service-accounts keys create model-armor-key.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 4. Copy the JSON content (do NOT commit this file!)
cat model-armor-key.json

# Output will be:
# {
#   "type": "service_account",
#   "project_id": "your-project",
#   "private_key_id": "...",
#   "private_key": "-----BEGIN PRIVATE KEY-----\n...",
#   ...
# }

# 5. Delete the file (we'll use env var instead)
rm model-armor-key.json

# NEVER commit the JSON file to git!
echo "model-armor-key.json" >> .gitignore
```

**Railway Configuration**:

1. Go to Railway dashboard
2. Select your project
3. Click "Variables" tab
4. Add variable:
   - **Name**: `MODEL_ARMOR_SERVICE_ACCOUNT_JSON`
   - **Value**: Paste the entire JSON content (as a single line or multi-line)

```bash
# Example (in Railway UI):
MODEL_ARMOR_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"your-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}
```

5. Add other variables:

```bash
MODEL_ARMOR_ENABLED=true
MODEL_ARMOR_PROJECT_ID=your-project-id
MODEL_ARMOR_LOCATION=us-central1
MODEL_ARMOR_TEMPLATE_ID=aegra-staging
```

**Verification**:

```bash
# In Railway logs, should see:
# [MODEL_ARMOR] Using service account JSON from environment variable
# [MODEL_ARMOR] Middleware enabled (project=your-project-id, ...)
```

## Security Best Practices

### Local Development
- ✅ Use ADC (gcloud auth application-default login)
- ✅ Use separate dev/test GCP project
- ✅ Use separate Model Armor template with lenient policies
- ❌ Never commit service account keys

### Staging (Railway)
- ✅ Use environment variable JSON method
- ✅ Store key in Railway secrets (encrypted)
- ✅ Use separate staging GCP project
- ✅ Rotate keys every 90 days
- ❌ Never commit keys to git
- ❌ Never share keys in Slack/email

### Production (GKE)
- ✅ Use Workload Identity (no keys!)
- ✅ Use separate production GCP project
- ✅ Enable audit logging
- ✅ Monitor service account usage
- ✅ Use strict Model Armor policies
- ❌ Never use JSON key files in production

## Troubleshooting

### Error: "Failed to generate Model Armor access token"

**For ADC (Method 1)**:
```bash
# Re-authenticate
gcloud auth application-default login

# Verify project
gcloud config get-value project

# Check credentials file exists
ls -la ~/.config/gcloud/application_default_credentials.json
```

**For Environment Variable (Method 3)**:
```bash
# Check JSON is valid
echo $MODEL_ARMOR_SERVICE_ACCOUNT_JSON | jq .

# Check all required fields present
echo $MODEL_ARMOR_SERVICE_ACCOUNT_JSON | jq 'keys'
# Should include: type, project_id, private_key_id, private_key, client_email
```

**For Workload Identity (Method 2)**:
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

### Error: "Permission denied"

```bash
# Check service account has correct role
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:model-armor-sa@*"

# Should show: roles/modelarmor.user

# If missing, add it:
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/modelarmor.user"
```

### Error: "Model Armor API not enabled"

```bash
# Check if API is enabled
gcloud services list --enabled | grep modelarmor

# Enable it
gcloud services enable modelarmor.googleapis.com
```

## Key Rotation (for Methods with Keys)

### For Environment Variable Method (Railway)

```bash
# 1. Create new key
gcloud iam service-accounts keys create model-armor-key-new.json \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 2. Update Railway environment variable with new key
# (Copy JSON content to MODEL_ARMOR_SERVICE_ACCOUNT_JSON)

# 3. Restart deployment to pick up new key

# 4. Verify new key works (check logs)

# 5. Delete old key
gcloud iam service-accounts keys list \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=model-armor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 6. Delete local file
rm model-armor-key-new.json
```

**Recommended rotation schedule**: Every 90 days

### For Workload Identity (GKE)

No rotation needed! GKE handles credential rotation automatically.

## Quick Reference

| Environment | Method | Auth Variable | Key File? |
|-------------|--------|---------------|-----------|
| Local Dev | ADC (gcloud CLI) | None | No |
| Railway Staging | Env Var JSON | `MODEL_ARMOR_SERVICE_ACCOUNT_JSON` | No (in env var) |
| GKE Production | Workload Identity | None | No |

## Testing Your Setup

```bash
# 1. Set environment variables (based on your method)

# 2. Start server
uv run uvicorn src.agent_server.main:app --reload

# 3. Check startup logs
# Should see:
# [MODEL_ARMOR] Using <method> for authentication
# [MODEL_ARMOR] Middleware enabled (project=..., ...)

# 4. Test with API call
TOKEN=$(uv run python scripts/generate_jwt_token.py --sub test-user)

curl -X POST http://localhost:8000/assistants/ava_v1/threads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"

# 5. Send test message
THREAD_ID=<thread-id-from-above>

curl -X POST http://localhost:8000/threads/$THREAD_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Book me a hotel in Miami"}'

# 6. Check logs for Model Armor activity
# Should see:
# [MODEL_ARMOR] Sanitizing user prompt (length=30)
# [MODEL_ARMOR] User prompt passed sanitization
# [MODEL_ARMOR] Sanitizing model response (length=...)
# [MODEL_ARMOR] Model response passed sanitization
```

## Next Steps

1. **Local Development**: Start with ADC method (easiest)
2. **Test Policies**: Use dev/test GCP project with lenient policies
3. **Staging**: Deploy to Railway with environment variable method
4. **Production**: Use Workload Identity on GKE (most secure)
5. **Monitor**: Review violation logs and tune policies
6. **Rotate**: Set calendar reminder for key rotation (if using keys)

## Additional Resources

- [Google Cloud Authentication Overview](https://cloud.google.com/docs/authentication)
- [Workload Identity Documentation](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Model Armor API Documentation](https://cloud.google.com/model-armor/docs)
