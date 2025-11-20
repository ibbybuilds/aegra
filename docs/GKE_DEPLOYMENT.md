# GKE Production Deployment Guide

This guide covers deploying Aegra to Google Kubernetes Engine (GKE) for production. The current setup builds and pushes Docker images to Google Container Registry via GitHub Actions - Kubernetes deployment configuration will be added in the future.

## Current Status

✅ **Implemented:**
- Production-optimized Dockerfile (`deployments/docker/Dockerfile.production`)
- GitHub Actions workflow for building and pushing images
- Multi-stage build with health checks
- Database migrations in container startup

⏳ **Coming Soon:**
- Kubernetes manifests (Deployment, Service, Ingress)
- Helm chart for flexible configuration
- Automated deployment from GitHub Actions
- Infrastructure as Code (Terraform)

## Prerequisites

- Google Cloud Platform account with billing enabled
- GCP project created
- `gcloud` CLI installed and configured
- `kubectl` installed
- GitHub repository with Aegra codebase
- Docker installed locally (for testing)

## Architecture Overview

```
GitHub Actions (on push to main)
          ↓
Build Docker image (Dockerfile.production)
          ↓
Push to GCR/Artifact Registry
          ↓
(Manual) Deploy to GKE cluster
          ↓
Pod connects to Cloud SQL for PostgreSQL
Pod optionally connects to Memorystore for Redis
```

## Step 1: Set Up GCP Services

### 1.1 Create GCP Project

```bash
# Set your project ID
export PROJECT_ID="aegra-production"

# Create project
gcloud projects create $PROJECT_ID

# Set as active project
gcloud config set project $PROJECT_ID

# Enable billing (required for Cloud SQL, GKE, etc.)
# Do this in the GCP Console: https://console.cloud.google.com/billing
```

### 1.2 Enable Required APIs

```bash
# Enable necessary GCP APIs
gcloud services enable \
  container.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  servicenetworking.googleapis.com
```

### 1.3 Set Up Artifact Registry

```bash
# Create Artifact Registry repository for Docker images
gcloud artifacts repositories create aegra \
  --repository-format=docker \
  --location=us-central1 \
  --description="Aegra Docker images"

# Configure Docker to use Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

## Step 2: Set Up Cloud SQL for PostgreSQL

Cloud SQL for PostgreSQL is fully compatible with LangGraph's `AsyncPostgresSaver` and `AsyncPostgresStore`.

### 2.1 Create Cloud SQL Instance

```bash
# Create PostgreSQL 15 instance
gcloud sql instances create aegra-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-type=SSD \
  --storage-size=10GB \
  --storage-auto-increase \
  --backup \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=3

# Create database
gcloud sql databases create aegra_prod \
  --instance=aegra-postgres

# Create user
gcloud sql users create aegra_user \
  --instance=aegra-postgres \
  --password=SECURE_PASSWORD_HERE
```

### 2.2 Configure Private IP (Recommended for Production)

```bash
# Create private IP connection
gcloud compute addresses create google-managed-services-default \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=default

# Create private service connection
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default \
  --network=default

# Update instance to use private IP
gcloud sql instances patch aegra-postgres \
  --network=default \
  --no-assign-ip
```

### 2.3 Get Connection Info

```bash
# Get private IP address
gcloud sql instances describe aegra-postgres \
  --format="value(ipAddresses.ipAddress)"

# Connection string format for Aegra:
# postgresql+asyncpg://aegra_user:SECURE_PASSWORD@PRIVATE_IP:5432/aegra_prod
```

## Step 3: Set Up Memorystore for Redis (Optional)

If you plan to use Redis for caching or sessions:

```bash
# Create Redis instance
gcloud redis instances create aegra-redis \
  --size=1 \
  --region=us-central1 \
  --tier=basic

# Get connection info
gcloud redis instances describe aegra-redis \
  --region=us-central1 \
  --format="value(host, port)"

# Connection string format:
# redis://REDIS_HOST:6379
```

## Step 4: Configure GitHub Actions

### 4.1 Create Service Account

```bash
# Create service account for GitHub Actions
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions CI/CD"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@${PROJECT_ID}.iam.gserviceaccount.com

# IMPORTANT: Store this key securely, you'll add it to GitHub Secrets
```

### 4.2 Configure GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Value | Description |
|------------|-------|-------------|
| `GCP_PROJECT_ID` | Your GCP project ID | e.g., `aegra-production` |
| `GCP_SA_KEY` | Contents of `github-actions-key.json` | Entire JSON file contents |
| `GCR_REGISTRY` | Registry path | e.g., `us-central1-docker.pkg.dev/aegra-production/aegra` |

## Step 5: Test Production Dockerfile Locally

Before deploying, test the production Dockerfile:

```bash
# Build the image
docker build -f deployments/docker/Dockerfile.production -t aegra:test .

# Run with environment variables
docker run --rm \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
  -e AUTH_TYPE=noop \
  -e OPENAI_API_KEY=sk-... \
  -p 8000:8000 \
  aegra:test

# Test health check
curl http://localhost:8000/health
```

## Step 6: Create GKE Cluster

```bash
# Create GKE cluster
gcloud container clusters create aegra-production \
  --region=us-central1 \
  --num-nodes=2 \
  --machine-type=e2-medium \
  --enable-autoscaling \
  --min-nodes=2 \
  --max-nodes=10 \
  --enable-autorepair \
  --enable-autoupgrade \
  --network=default

# Get cluster credentials
gcloud container clusters get-credentials aegra-production \
  --region=us-central1
```

## Step 7: Deploy to GKE (Manual for Now)

### 7.1 Create Kubernetes Secrets

```bash
# Create secret for database URL
kubectl create secret generic aegra-secrets \
  --from-literal=database-url='postgresql+asyncpg://aegra_user:PASSWORD@PRIVATE_IP:5432/aegra_prod' \
  --from-literal=openai-api-key='sk-proj-...' \
  --from-literal=auth-type='custom'
```

### 7.2 Example Deployment (Basic)

Create a file `k8s-deployment-example.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegra
spec:
  replicas: 2
  selector:
    matchLabels:
      app: aegra
  template:
    metadata:
      labels:
        app: aegra
    spec:
      containers:
      - name: aegra
        image: us-central1-docker.pkg.dev/aegra-production/aegra/aegra:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: aegra-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: aegra-secrets
              key: openai-api-key
        - name: AUTH_TYPE
          valueFrom:
            secretKeyRef:
              name: aegra-secrets
              key: auth-type
        - name: PORT
          value: "8000"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 40
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: aegra-service
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8000
  selector:
    app: aegra
```

Apply:
```bash
kubectl apply -f k8s-deployment-example.yaml
```

## CI/CD Workflow

The GitHub Actions workflow (`.github/workflows/production.yml`) automatically:

1. Runs on push to `main` branch
2. Executes full CI checks (linting, type-checking, security)
3. Runs E2E tests with PostgreSQL
4. Builds production Docker image
5. Tags with git SHA and `latest`
6. Pushes to Google Artifact Registry

The image will be available at:
```
us-central1-docker.pkg.dev/PROJECT_ID/aegra/aegra:sha-abc1234
us-central1-docker.pkg.dev/PROJECT_ID/aegra/aegra:latest
```

**Manual deployment required**: After the image is pushed, manually update your K8s deployment to use the new image.

## Database Compatibility

✅ **Cloud SQL for PostgreSQL is 100% compatible** with Aegra's LangGraph integration:
- LangGraph uses `AsyncPostgresSaver` (checkpoints)
- LangGraph uses `AsyncPostgresStore` (long-term memory)
- Both use standard PostgreSQL protocol
- Cloud SQL is fully PostgreSQL-compatible

No code changes needed - just update the `DATABASE_URL` connection string.

## Monitoring and Logging

### GCP Cloud Logging

```bash
# View logs
gcloud logging read "resource.type=k8s_container AND resource.labels.cluster_name=aegra-production" \
  --limit=50 \
  --format=json
```

### GCP Cloud Monitoring

Set up alerts in GCP Console:
- Pod CPU/Memory usage
- HTTP error rates
- Database connection errors
- Health check failures

### Langfuse (Optional)

Configure Langfuse in your Kubernetes secrets for LLM observability.

## Cost Estimation

Approximate monthly costs:

| Service | Configuration | Est. Cost |
|---------|--------------|-----------|
| GKE Cluster | 2x e2-medium nodes | ~$50-70/month |
| Cloud SQL | db-f1-micro, 10GB | ~$25-35/month |
| Memorystore Redis | Basic, 1GB (optional) | ~$25/month |
| Artifact Registry | <10GB storage | ~$1-2/month |
| Network Egress | Depends on traffic | Variable |
| **Total** | Without Redis | **~$75-105/month** |

**Tips:**
- Use autoscaling to reduce costs during low traffic
- Consider preemptible nodes for non-critical workloads
- Set up budget alerts in GCP Console

## Security Best Practices

1. **Network Security**:
   - Use private IPs for Cloud SQL (no public internet access)
   - Configure VPC firewall rules
   - Use GKE Workload Identity for service authentication

2. **Secrets Management**:
   - Store secrets in Kubernetes Secrets or GCP Secret Manager
   - Never commit secrets to git
   - Rotate database passwords regularly

3. **Container Security**:
   - Run as non-root user (already configured in Dockerfile)
   - Scan images for vulnerabilities
   - Keep base images updated

4. **Application Security**:
   - Use `AUTH_TYPE=custom` in production
   - Implement rate limiting
   - Enable CORS with specific origins

## Troubleshooting

### Issue: Database connection fails

**Check:**
- Cloud SQL instance is running
- Private IP is accessible from GKE cluster (same VPC)
- Connection string format: `postgresql+asyncpg://...`
- Database user has correct permissions

### Issue: Image pull errors

**Check:**
- GKE cluster has permissions to pull from Artifact Registry
- Image tag exists in registry
- Registry URL is correct in deployment YAML

### Issue: Migrations fail on startup

**Check:**
- Database user has DDL permissions (CREATE TABLE, ALTER TABLE)
- Alembic files are included in Docker image
- Check pod logs: `kubectl logs <pod-name>`

## Next Steps

- [ ] Create Helm chart for easier configuration management
- [ ] Add Kubernetes manifests (Deployment, Service, Ingress, HPA)
- [ ] Set up automated deployment from GitHub Actions
- [ ] Configure GKE Ingress with SSL/TLS
- [ ] Set up monitoring and alerting
- [ ] Implement Infrastructure as Code (Terraform)
- [ ] Add CI/CD for database migrations
- [ ] Configure backup and disaster recovery

## Resources

- [GKE Documentation](https://cloud.google.com/kubernetes-engine/docs)
- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [LangGraph Checkpoint Postgres](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres)
