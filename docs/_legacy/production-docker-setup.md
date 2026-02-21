# Production Docker Setup

This document outlines ideas for creating a production-ready Docker Compose setup, separate from the current development-focused configuration.

## Current State

The current `docker-compose.yml` is optimized for **development** with:
- `--reload` flag for hot-reloading code changes
- Source code volume mounts (`./src:/app/src:ro`)
- Config file mounts (`aegra.json`, `auth.py`, custom routes)
- `DEBUG=true` environment variable
- Exposed database/Redis ports for local access
- Hardcoded credentials for quick setup

## Production Requirements

### Security Improvements

1. **Secrets Management**
   - Remove hardcoded credentials (`user:password`)
   - Use Docker secrets or environment variables from secrets manager
   - Don't mount `.env` file - inject via environment

2. **Network Security**
   - Don't expose database/Redis ports externally
   - Use internal Docker networks for service communication
   - Remove unnecessary port mappings

3. **File Security**
   - Remove source code volume mounts (code baked into image)
   - Config files baked into image or managed via config service
   - Read-only file system where possible

### Performance Optimizations

1. **Remove Development Features**
   - Remove `--reload` flag
   - Remove debug logging (`DEBUG=false`)

2. **Resource Management**
   - Add resource limits (`cpus`, `memory`)
   - Add restart policies (`restart: unless-stopped`)
   - Configure connection pooling limits

3. **Optimized Startup**
   - Migrations run automatically on server startup (as of v0.3.0)
   - Health checks for all services
   - Graceful shutdown handling

### Configuration Management

1. **Environment-Specific Configs**
   - Separate configs for dev/staging/prod
   - Use environment variables for runtime configuration
   - Config files baked into image or mounted from secure location

2. **Custom Routes**
   - Custom route files baked into image (not mounted)
   - Or mounted from secure, versioned location
   - No hot-reload in production

## Proposed Solution: Dual Compose Files

Use Docker Compose override pattern:
- `docker-compose.yml` - Base development setup
- `docker-compose.prod.yml` - Production overrides

### Example Production Override

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  aegra:
    # Override command: remove --reload for production
    # Migrations run automatically on startup (v0.3.0+)
    command: >
      uvicorn aegra_api.main:app --host 0.0.0.0 --port $${PORT:-8000}

    # Remove development volume mounts (code baked in)
    volumes:
      - postgres_data:/var/lib/postgresql  # Only data volumes

    # Production environment
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - ENV_MODE=PRODUCTION

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

    # Restart policy
    restart: unless-stopped

    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  postgres:
    # Don't expose port externally
    ports: []

    # Use secrets for credentials
    environment:
      - POSTGRES_USER_FILE=/run/secrets/postgres_user
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
      - POSTGRES_DB=aegra

    secrets:
      - postgres_user
      - postgres_password

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G

    restart: unless-stopped

  redis:
    # Don't expose port externally
    ports: []

    # Production Redis config
    command: >
      redis-server
      --appendonly yes
      --maxmemory 1gb
      --maxmemory-policy allkeys-lru
      --requirepass ${REDIS_PASSWORD}

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

    restart: unless-stopped

secrets:
  postgres_user:
    external: true
  postgres_password:
    external: true
```

### Usage

```bash
# Development (current setup)
docker-compose up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Create secrets first
echo "postgres_user" | docker secret create postgres_user -
echo "secure_password" | docker secret create postgres_password -
```

## Alternative: Separate Production Compose File

Instead of overrides, create completely separate `docker-compose.production.yml`:

**Pros:**
- Clear separation between dev and prod
- No risk of accidentally using dev configs
- Easier to maintain different architectures

**Cons:**
- Duplication of service definitions
- Need to keep both files in sync

## Additional Production Considerations

### 1. Multi-Stage Build Optimization

The Dockerfile already uses multi-stage builds, but could be optimized:
- Separate build cache layers
- Minimize final image size
- Use `.dockerignore` to exclude dev files

### 2. Logging and Monitoring

- Structured JSON logging (already have structlog)
- Log aggregation (ELK, Loki, etc.)
- Metrics endpoint for Prometheus
- Health check endpoints (already have `/health`, `/ready`, `/live`)

### 3. High Availability

- Multiple API server replicas
- Database replication
- Redis sentinel/cluster for HA
- Load balancer (nginx, traefik)

### 4. CI/CD Integration

- Build images in CI
- Push to registry
- Deploy via compose or Kubernetes
- Automated testing before deployment

### 5. Backup and Recovery

- Database backup strategy
- Redis persistence configuration
- Disaster recovery procedures

## Migration Path

1. **Phase 1**: Create `docker-compose.prod.yml` override file
2. **Phase 2**: Test production setup in staging environment
3. **Phase 3**: Document production deployment procedures
4. **Phase 4**: Set up secrets management
5. **Phase 5**: Add monitoring and alerting
6. **Phase 6**: Implement HA setup if needed

## References

- [Docker Compose Override Pattern](https://docs.docker.com/compose/extends/)
- [Docker Secrets](https://docs.docker.com/engine/swarm/secrets/)
- [Production Best Practices](https://docs.docker.com/develop/dev-best-practices/)
