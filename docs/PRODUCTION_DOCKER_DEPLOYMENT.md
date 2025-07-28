# DispatchAI Production Docker Deployment Guide

## Overview

This guide covers deploying DispatchAI using Docker Compose for production environments. This approach is more reliable than Fly.io for microservices that need constant connectivity, as it avoids the automatic sleep/wake behavior of serverless platforms.

## Architecture

The production deployment uses Docker Compose to orchestrate:

- **PostgreSQL 16** with pgvector extension
- **Redpanda** (Kafka-compatible message queue)
- **Ingress Service** (FastAPI webhook receiver)
- **Classifier Service** (AI-powered analysis)
- **Gateway Service** (WebSocket/REST API)
- **Dashboard** (React frontend)
- **Redpanda Console** (optional Kafka management UI)

## Prerequisites

### System Requirements
- Docker and Docker Compose installed
- Minimum 4GB RAM recommended
- 10GB free disk space for data volumes
- Ports 3000, 8000, 8001, 8002, 5432, 19092 available

### Required API Keys
- OpenAI API key (required for AI classification)
- Anthropic API key (optional, for future Claude integration)

## Quick Start

### 1. Environment Setup

```bash
# Copy the environment template
cp .env.prod.example .env.prod

# Edit with your configuration
nano .env.prod
```

**Required Environment Variables:**
```bash
# Database password (set a strong password)
POSTGRES_PASSWORD=your_secure_database_password_here

# OpenAI API key (required)
OPENAI_API_KEY=your_openai_api_key_here

# Optional: GitHub webhook secret for security
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret
```

### 2. Start Production Environment

```bash
# Use the provided startup script
./scripts/start-prod.sh
```

Or manually:
```bash
# Build images
docker compose -f docker-compose.prod.yml --env-file .env.prod build

# Start services
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Check status
docker compose -f docker-compose.prod.yml ps
```

### 3. Verify Deployment

**Service Health Checks:**
```bash
# Gateway API
curl http://localhost:8002/health

# Ingress webhook receiver  
curl http://localhost:8000/health

# Classifier service
curl http://localhost:8001/health

# Dashboard
curl http://localhost:3000/health
```

**Test Complete Pipeline:**
```bash
# Check API functionality
curl http://localhost:8002/api/stats

# Test webhook endpoint
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -d '{"test": "webhook"}'
```

## Service URLs

- **📊 Dashboard**: http://localhost:3000
- **🌐 Gateway API**: http://localhost:8002
- **📥 Webhook Ingress**: http://localhost:8000
- **🤖 AI Classifier**: http://localhost:8001 (internal)
- **🗄️ Database**: postgresql://localhost:5432/dispatchai
- **📡 Kafka**: localhost:19092
- **🖥️ Kafka Console**: http://localhost:8080 (with --profile tools)

## Management Commands

### Start/Stop
```bash
# Start all services
./scripts/start-prod.sh

# Stop all services  
./scripts/stop-prod.sh

# Or manually
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml down
```

### Monitoring
```bash
# View all logs
docker compose -f docker-compose.prod.yml logs -f

# View specific service logs
docker compose -f docker-compose.prod.yml logs -f gateway

# Check service status
docker compose -f docker-compose.prod.yml ps

# View resource usage
docker stats
```

### Maintenance
```bash
# Restart a specific service
docker compose -f docker-compose.prod.yml restart gateway

# Rebuild and restart service after code changes
docker compose -f docker-compose.prod.yml up -d --build gateway

# Access database
docker exec -it dispatchai-postgres-prod psql -U postgres -d dispatchai

# Access Kafka console
docker exec -it dispatchai-redpanda-prod rpk topic list
```

## Data Persistence

### Volume Management
```bash
# List volumes
docker volume ls | grep dispatchai

# Backup database
docker exec dispatchai-postgres-prod pg_dump -U postgres dispatchai > backup.sql

# Backup volumes
docker run --rm -v dispatchai_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz -C /data .
```

### Reset Data (⚠️ Destructive)
```bash
# Stop services and remove all data
docker compose -f docker-compose.prod.yml down -v

# Remove all DispatchAI containers and images
docker system prune -f
```

## Production Considerations

### Security
- Change default database password
- Set GitHub webhook secret
- Use HTTPS reverse proxy (nginx/Traefik)
- Implement proper firewall rules
- Regular security updates

### Performance Tuning
```yaml
# In docker-compose.prod.yml, adjust resource limits:
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

### Scaling
```yaml
# Scale services for higher load:
services:
  classifier:
    deploy:
      replicas: 3
  gateway:
    deploy:
      replicas: 2
```

### Monitoring
- Add Prometheus/Grafana for metrics
- Set up log aggregation (ELK stack)
- Configure health check alerts
- Monitor disk space and database performance

## Reverse Proxy Setup (Nginx)

For production domains, use nginx as a reverse proxy:

```nginx
# /etc/nginx/sites-available/dispatchai
server {
    listen 80;
    server_name yourdomain.com;

    # Dashboard
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API Gateway
    location /api/ {
        proxy_pass http://localhost:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Webhook ingress
    location /webhook/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check logs for errors
docker compose -f docker-compose.prod.yml logs

# Verify environment variables
docker compose -f docker-compose.prod.yml config

# Check port conflicts
netstat -tlnp | grep -E ':(3000|8000|8001|8002|5432|19092)'
```

**Database connection errors:**
```bash
# Verify database is running
docker compose -f docker-compose.prod.yml ps postgres

# Test connection
docker exec dispatchai-postgres-prod pg_isready -U postgres

# Check database logs
docker compose -f docker-compose.prod.yml logs postgres
```

**Kafka connection issues:**
```bash
# Check Redpanda health
docker exec dispatchai-redpanda-prod rpk cluster health

# List topics
docker exec dispatchai-redpanda-prod rpk topic list

# View Kafka logs
docker compose -f docker-compose.prod.yml logs redpanda
```

**AI classification not working:**
```bash
# Verify OpenAI API key
docker compose -f docker-compose.prod.yml exec classifier env | grep OPENAI

# Check classifier logs
docker compose -f docker-compose.prod.yml logs classifier
```

### Performance Issues

**High memory usage:**
```bash
# Monitor container resources
docker stats

# Adjust memory limits in docker-compose.prod.yml
# Increase host system RAM if needed
```

**Slow response times:**
```bash
# Check database performance
docker exec dispatchai-postgres-prod psql -U postgres -d dispatchai -c "SELECT * FROM pg_stat_activity;"

# Monitor Kafka consumer lag
docker exec dispatchai-redpanda-prod rpk group describe dispatchai-gateway
```

## Backup and Recovery

### Automated Backup Script
```bash
#!/bin/bash
# backup-prod.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"
mkdir -p $BACKUP_DIR

# Database backup
docker exec dispatchai-postgres-prod pg_dump -U postgres dispatchai > $BACKUP_DIR/database.sql

# Volume backup
docker run --rm -v dispatchai_postgres_data:/data -v $(pwd)/backups/$DATE:/backup alpine tar czf /backup/postgres-data.tar.gz -C /data .
docker run --rm -v dispatchai_redpanda_data:/data -v $(pwd)/backups/$DATE:/backup alpine tar czf /backup/redpanda-data.tar.gz -C /data .

echo "Backup completed: $BACKUP_DIR"
```

### Recovery
```bash
# Stop services
docker compose -f docker-compose.prod.yml down

# Restore database
docker compose -f docker-compose.prod.yml up -d postgres
docker exec -i dispatchai-postgres-prod psql -U postgres -d dispatchai < backup/database.sql

# Restore volumes if needed
docker run --rm -v dispatchai_postgres_data:/data -v $(pwd)/backup:/backup alpine tar xzf /backup/postgres-data.tar.gz -C /data

# Start all services
docker compose -f docker-compose.prod.yml up -d
```

## Deployment Comparison

| Feature | Docker Compose | Fly.io |
|---------|----------------|--------|
| **Reliability** | ✅ Always-on services | ❌ Auto-sleep causes issues |
| **Cost** | 💰 Server hosting required | 💰 Free tier with limitations |
| **Maintenance** | 🔧 Manual updates needed | ✅ Automatic platform updates |
| **Scaling** | 🔧 Manual scaling | ✅ Automatic scaling |
| **Data Persistence** | ✅ Full control | ❌ Volume limitations |
| **Network Connectivity** | ✅ Stable inter-service comms | ❌ Services can be unreachable |
| **Development Parity** | ✅ Identical to dev environment | ❌ Different platform behavior |

## Conclusion

Docker Compose production deployment provides:
- **Reliability**: No auto-sleep interruptions
- **Control**: Full control over services and data
- **Cost-effectiveness**: Predictable hosting costs
- **Simplicity**: Similar to development environment
- **Scalability**: Can scale services based on load

This approach is recommended for DispatchAI's microservices architecture where constant service availability and inter-service communication are critical.

---

**Created**: July 28, 2025  
**Last Updated**: July 28, 2025  
**Version**: 1.0