# Railway Staging Deployment Guide

This guide walks you through deploying Aegra to Railway for your staging environment, with automatic deployments from the `development` branch.

## Prerequisites

- Railway account ([sign up at railway.app](https://railway.app))
- GitHub repository with Aegra codebase
- Access to configure environment variables

## Step 1: Create Railway Project

1. Log in to [Railway](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub account if prompted
5. Select your Aegra repository

## Step 2: Configure GitHub Integration

1. In the Railway project settings, go to **"GitHub"** section
2. Select the **`development`** branch for automatic deployments
3. Enable **"Auto-deploy"** - Railway will now deploy automatically on every push to `development`

## Step 3: Add PostgreSQL Service

Railway will use the existing `Dockerfile` in `deployments/docker/Dockerfile` for your app. Now add the database:

1. In your Railway project, click **"New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway will automatically:
   - Provision a PostgreSQL 15 instance
   - Create a `DATABASE_URL` environment variable
   - Connect it to your Aegra service

3. **Important**: Update the DATABASE_URL format:
   - Railway provides: `postgresql://user:pass@host:port/db`
   - Aegra needs: `postgresql+asyncpg://user:pass@host:port/db`
   - In the Aegra service settings, edit the `DATABASE_URL` variable and add `+asyncpg` after `postgresql`

## Step 4: Configure Environment Variables

In your Aegra service settings, go to **"Variables"** and add the following (use `.env.staging.example` as reference):

### Required Variables

```bash
# Railway auto-provides DATABASE_URL - just add +asyncpg as shown above
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db

# Authentication (use noop for staging)
AUTH_TYPE=noop

# LLM Provider (choose one or more)
OPENAI_API_KEY=sk-proj-...
# ANTHROPIC_API_KEY=sk-ant-...

# Server config (Railway auto-sets PORT, but you can set DEBUG)
DEBUG=true
```

### Optional Variables

```bash
# Langfuse observability (recommended for monitoring)
LANGFUSE_LOGGING=true
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Redis (if you add Redis service later)
# REDIS_URL=redis://default:password@redis.railway.internal:6379
```

### AVA-core Variables

Add any additional environment variables required by your `ava-core` package.

## Step 5: Configure Health Check

1. In service settings, go to **"Health Check"**
2. Set health check path: `/health`
3. Railway will use this to verify your service is running

## Step 6: Verify Deployment

1. Railway will automatically trigger the first deployment
2. Monitor the deployment in the **"Deployments"** tab
3. Check the logs for any errors during:
   - Docker build
   - Database migrations (`alembic upgrade head`)
   - Server startup

4. Once deployed, Railway provides a URL like: `https://aegra-staging-production.up.railway.app`
5. Test the deployment:
   ```bash
   curl https://your-railway-url.railway.app/health
   ```

## Step 7: Custom Domain (Optional)

1. In service settings, go to **"Settings"** → **"Networking"**
2. Click **"Add Custom Domain"**
3. Follow Railway's instructions to configure DNS
4. Example: `staging.aegra.yourdomain.com`

## Deployment Workflow

Once configured, the deployment workflow is:

```
Developer pushes to `development` branch
          ↓
GitHub Actions runs CI checks (.github/workflows/development-ci.yml)
  - Linting, type-checking, security scan
  - Unit tests
  - E2E tests with PostgreSQL
          ↓
If CI passes, Railway automatically detects the push
          ↓
Railway builds Docker image (deployments/docker/Dockerfile)
          ↓
Railway runs migrations and starts server
          ↓
Railway performs health check on /health endpoint
          ↓
New version deployed to staging URL
```

## Troubleshooting

### Issue: Database connection errors

**Symptom**: Logs show `connection refused` or `could not connect to server`

**Solution**:
1. Verify `DATABASE_URL` has `+asyncpg` suffix: `postgresql+asyncpg://...`
2. Check PostgreSQL service is running in Railway dashboard
3. Ensure database and app services are in the same Railway project

### Issue: Migration failures

**Symptom**: `alembic upgrade head` fails during startup

**Solution**:
1. Check that `alembic/` directory and `alembic.ini` are included in the build
2. Verify database user has permission to create tables
3. Check logs for specific Alembic error messages

### Issue: Environment variables not available

**Symptom**: Server starts but LLM calls fail or auth errors occur

**Solution**:
1. Verify all required variables are set in Railway service settings
2. Check for typos in variable names (they are case-sensitive)
3. Restart the service after adding new variables

### Issue: Health check failing

**Symptom**: Railway shows service as unhealthy or keeps restarting

**Solution**:
1. Verify `/health` endpoint is accessible: `curl https://your-url.railway.app/health`
2. Check server logs for startup errors
3. Ensure `PORT` environment variable is not hardcoded (Railway sets it automatically)

### Issue: Build failures

**Symptom**: Docker build fails during Railway deployment

**Solution**:
1. Check that all files referenced in Dockerfile exist (aegra.json, auth.py, graphs/)
2. Verify `pyproject.toml` dependencies can be resolved
3. Check Railway build logs for specific error messages
4. Test the Dockerfile locally: `docker build -f deployments/docker/Dockerfile .`

## Monitoring and Logs

### View Logs
- Railway Dashboard → Your Service → **"Logs"** tab
- Real-time log streaming
- Filter by log level

### Metrics
- Railway Dashboard → Your Service → **"Metrics"** tab
- CPU and memory usage
- Request metrics (if configured)

### Langfuse (Optional)
If configured, view detailed LLM observability at [cloud.langfuse.com](https://cloud.langfuse.com):
- Token usage
- Latency metrics
- Cost tracking
- Error rates

## Rollback

If a deployment has issues:

1. In Railway dashboard, go to **"Deployments"** tab
2. Find the last working deployment
3. Click **"Redeploy"** on that deployment
4. Railway will instantly rollback to that version

## Cost Optimization

Railway offers:
- **Free tier**: Suitable for small staging environments
- **Pro plan**: $5/month (includes more resources)
- **Database**: ~$5-10/month for PostgreSQL (starter tier)

**Tip**: Set resource limits in service settings to control costs

## Next Steps

- Set up custom domain for staging
- Configure Langfuse for observability
- Add Redis service if needed for caching
- Set up automated tests that run against staging after deployment
- Configure alerting for deployment failures

## Support

- Railway Documentation: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Aegra Issues: https://github.com/yourusername/aegra/issues
