# Infrastructure

Docker Compose and deployment configurations.

## Purpose

This directory contains all infrastructure-related configurations including Docker Compose for local development and Fly.io configurations for production deployment.

## Contents

- `docker-compose.yml` - Local development environment with all services
- `init-db.sql` - PostgreSQL database initialization script
- Environment variable templates
- Database migration scripts (coming soon)
- Monitoring configurations (coming soon)

## Quick Start

1. **Set up environment variables:**
   ```bash
   # Copy the example environment file
   cp .env.example .env

   # Edit .env with your actual values:
   # - POSTGRES_PASSWORD (set a secure password)
   # - GITHUB_WEBHOOK_SECRET (for webhook validation)
   # - OPENAI_API_KEY (for AI classification)
   # - ANTHROPIC_API_KEY (optional, for additional AI models)
   ```

2. **Start the development environment:**
   ```bash
   cd infra
   docker-compose up -d
   ```

3. **Verify services are running:**
   ```bash
   docker-compose ps
   ```

## Required Environment Variables

Create a `.env` file in the project root with these variables:

```bash
# Database Configuration
POSTGRES_DB=auto_triager
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password_here

# GitHub Integration
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
GITHUB_TOKEN=your_github_token_here

# AI/ML API Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Application Configuration
LOG_LEVEL=INFO
ENVIRONMENT=development

# React App Configuration
REACT_APP_API_URL=http://localhost:8001
REACT_APP_WS_URL=ws://localhost:8001/ws

# Development Configuration
CHOKIDAR_USEPOLLING=true
WATCHPACK_POLLING=true
```

## Services

### Core Infrastructure
- **Redpanda** (port 19092) - Kafka-compatible message broker
- **PostgreSQL 16** (port 5432) - Database with pgvector extension (using pgvector/pgvector:pg16)

### Application Services
- **Ingress** (port 8000) - FastAPI webhook receiver
- **Classifier** - LangChain AI worker service
- **Gateway** (port 8001) - WebSocket/REST API service
- **Dashboard** (port 3000) - React frontend application

## Database Schema

The `init-db.sql` script creates:
- `issues` - Raw GitHub issues
- `enriched_issues` - AI-processed issue data with vector embeddings
- `manual_corrections` - Human feedback for AI improvements
- `similar_issues` - Issue similarity relationships
- `processing_logs` - Monitoring and debugging logs

## Health Checks

All services include health checks:
- Redpanda: Cluster health via `rpk`
- PostgreSQL: Connection test via `pg_isready`
- Application services: Depend on healthy infrastructure

## Development Workflow

1. Start infrastructure: `docker-compose up redpanda postgres -d`
2. Verify database: `docker-compose exec postgres psql -U postgres -d auto_triager -c "\dt auto_triager.*"`
3. Start application services: `docker-compose up ingress classifier gateway dashboard -d`
4. Access dashboard: http://localhost:3000
5. View logs: `docker-compose logs -f [service_name]`

## Troubleshooting

- **Services won't start**: Check `.env` file exists and has required variables
- **Database connection issues**: Verify PostgreSQL is healthy: `docker-compose ps postgres`
- **Redpanda issues**: Check cluster health: `docker-compose exec redpanda rpk cluster health`
- **Port conflicts**: Ensure ports 3000, 5432, 8000, 8001, 19092 are available
