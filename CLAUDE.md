# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto-Triager is an intelligent GitHub issue classification and triaging system that automatically processes, enriches, and categorizes GitHub issues using AI-powered analysis. The system is built as a microservices architecture with real-time processing capabilities.

## Architecture

The system consists of four main microservices:

- **Ingress Service** (`/ingress`) - FastAPI webhook receiver for GitHub events (Port 8000)
- **Classifier Service** (`/classifier`) - LangChain-powered AI worker for issue analysis
- **Gateway Service** (`/gateway`) - WebSocket/REST API for real-time updates (Port 8002)
- **Dashboard** (`/dashboard`) - React frontend for monitoring and corrections (Port 3000)

Additional infrastructure includes:
- **PostgreSQL 16** with pgvector extension (Port 5432)
- **Redpanda** (Kafka-compatible message queue) (Port 19092)

## Essential Development Commands

All development is managed through the comprehensive Makefile:

### Start/Stop Environment
```bash
# Start complete development environment
make dev

# Stop development environment
make dev-down

# View logs from all services
make dev-logs

# Check service health
make status
```

### Testing
```bash
# Run all tests
make test

# Run individual component tests
make test-ingress
make test-classifier
make test-gateway
make test-dashboard
```

### Linting
```bash
# Run all linters
make lint

# Fix linting issues automatically
make lint-fix

# Python linting (uses ruff)
make lint-python

# JavaScript/TypeScript linting
make lint-js
```

### Database Management
```bash
# Reset database with fresh schema
make db-reset

# Open PostgreSQL shell
make db-shell

# Backup database
make db-backup
```

### Build Commands
```bash
# Build all Docker images
make build

# Build specific service
make build-service SERVICE=ingress
```

## Service-Specific Commands

### Dashboard (React/TypeScript)
Located in `/dashboard`:
```bash
cd dashboard
npm run dev      # Start development server
npm run build    # Build for production
npm run lint     # Run ESLint
```

### Python Services (ingress, classifier, gateway)
Each service uses similar patterns:
```bash
cd <service>
python -m pytest tests/ -v    # Run tests
ruff check .                  # Lint code
ruff format .                 # Format code
```

## Key Directories and Files

### Configuration Files
- `/infra/docker-compose.yml` - Main development environment configuration
- `/Makefile` - All development commands and targets
- `/.env` - Environment variables (create from template)
- `/dashboard/package.json` - Frontend dependencies and scripts

### Service Structure
Each service follows this pattern:
```
/<service>/
├── Dockerfile.dev          # Development container
├── Dockerfile             # Production container
├── app.py                 # Main application (Python services)
├── requirements.txt       # Python dependencies
├── requirements.in        # Dependency source
└── README.md             # Service-specific documentation
```

### Infrastructure
- `/infra/init-db.sql` - Database initialization script
- `/scripts/` - Utility scripts and project documentation

## Development Workflow

1. **Start Environment**: Run `make dev` to start all services
2. **Verify Health**: Use `make status` to ensure all services are running
3. **Make Changes**: Edit code in service directories (auto-reload enabled)
4. **Test**: Run `make test` for comprehensive testing
5. **Lint**: Run `make lint` before committing
6. **Database Changes**: Use `make db-reset` if schema changes are needed

## Environment Setup

The system uses environment variables for configuration:

### Required Variables
```bash
# API Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Database
POSTGRES_DB=auto_triager
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Service Configuration
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/auto_triager
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
```

Use `make setup-env` to create initial `.env` file template.

## Technology Stack

### Backend
- **FastAPI** - API framework for all Python services
- **LangChain** - AI processing framework
- **OpenAI API** - AI model integration
- **PostgreSQL 16** with pgvector - Database with vector search
- **Redpanda** - Kafka-compatible message streaming

### Frontend
- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and development server
- **ESLint** - Code linting

### Development
- **Docker Compose** - Containerized development
- **ruff** - Python formatting and linting
- **pytest** - Python testing framework

## Performance Requirements

The system is designed to handle:
- 1,000+ GitHub issues per minute
- Real-time processing and dashboard updates
- Vector similarity search for issue clustering
- Horizontal scaling support

## Service URLs (Development)

- Dashboard: http://localhost:3000
- API Gateway: http://localhost:8002 (WebSocket: ws://localhost:8002/ws)
- Ingress Webhooks: http://localhost:8000
- Database: postgresql://postgres:postgres@localhost:5432/auto_triager
- Redpanda Console: http://localhost:8080

## Testing Strategy

Each service should have comprehensive tests:
- **Unit tests** for individual functions
- **Integration tests** for API endpoints
- **End-to-end tests** for complete workflows

Use `./scripts/test-dev-environment.sh` to verify the complete environment.

## Deployment

The system is designed for deployment on Fly.io:
```bash
make deploy-fly
```

All services have production Dockerfiles and are configured for cloud deployment.

## Troubleshooting

### Common Issues
- **Port conflicts**: Check `lsof -i :3000 -i :8000 -i :8002 -i :5432 -i :19092`
- **Service startup failures**: Check `make dev-logs` for error details
- **Database issues**: Try `make db-reset` to recreate with fresh schema
- **Dependency conflicts**: Run `make dev-clean` followed by `make dev`

### Health Checks
All services expose health endpoints that can be tested:
- Ingress: http://localhost:8000/health
- Gateway: http://localhost:8002/health
- Dashboard: http://localhost:3000 (HTML response)

## Data Flow and System Design

### High-Level Data Pipeline
```
GitHub Issue Created
        ↓
[Ingress] Webhook Receiver → Validates & forwards to Kafka
        ↓
[Kafka] Raw Events Topic → Decouples ingestion from processing
        ↓
[Classifier] AI Worker → Consumes, analyzes, enriches with AI
        ↓
[Database] PostgreSQL + pgvector → Stores enriched data with vectors
        ↓
[Gateway] WebSocket/API → Real-time updates to frontend
        ↓
[Dashboard] React UI → Human review and corrections
```

### Key Design Patterns

#### Microservices Architecture
- **Service isolation**: Each service has single responsibility
- **Independent scaling**: Services scale based on individual load
- **Technology diversity**: Each service uses optimal tech stack
- **Failure containment**: One service failure doesn't cascade

#### Event-Driven Processing
- **Async communication**: Services communicate via Kafka messages
- **Replay capability**: Events can be reprocessed from any point
- **Audit trail**: Complete history of all issue processing
- **Loose coupling**: Services don't need direct knowledge of each other

#### AI Integration Patterns
- **Human-in-the-loop**: AI provides suggestions, humans provide oversight
- **Confidence scoring**: AI indicates certainty level of classifications
- **Feedback loops**: Human corrections improve future AI performance
- **Graceful degradation**: System works even if AI services are down

### Service Responsibilities

#### Ingress Service
- **Input validation**: GitHub webhook signature verification
- **Rate limiting**: Protect against abuse and traffic spikes
- **Event publishing**: Send raw events to Kafka for processing
- **Security hardening**: First line of defense for external requests

#### Classifier Service
- **AI processing**: LangChain + OpenAI for issue analysis
- **Vector generation**: Create embeddings for similarity search
- **Batch processing**: Handle multiple issues efficiently
- **Error recovery**: Retry failed classifications with backoff

#### Gateway Service
- **API endpoints**: REST API for dashboard and external integrations
- **Real-time updates**: WebSocket broadcasting of events
- **Data aggregation**: Combine data from database for frontend
- **Authentication**: Security layer for dashboard access

#### Dashboard Service
- **Real-time UI**: Live updates via WebSocket connections
- **Correction interface**: UI for human review and feedback
- **Analytics visualization**: Charts and insights on issue patterns
- **Responsive design**: Works on desktop and mobile devices

## Project Structure and Conventions

### Code Organization
```
/ingress/           # GitHub webhook receiver
  app.py            # Main FastAPI application
  models/           # Pydantic models for webhook payloads
  services/         # Business logic and external integrations
  tests/            # Unit and integration tests

/classifier/        # AI processing service
  app.py            # Main application and Kafka consumer
  ai/               # LangChain and AI model integrations
  models/           # Data models for issue classification
  tests/            # AI model and processing tests

/gateway/           # API and WebSocket service
  app.py            # FastAPI app with WebSocket support
  api/              # REST API endpoints
  websocket/        # Real-time WebSocket handlers
  tests/            # API and WebSocket tests

/dashboard/         # React frontend
  src/              # TypeScript React components
    components/     # Reusable UI components
    pages/          # Page-level components
    services/       # API client and WebSocket management
    types/          # TypeScript type definitions
  tests/            # Frontend unit and integration tests

/infra/             # Infrastructure configuration
  docker-compose.yml    # Development environment
  init-db.sql          # Database schema initialization
  
/tasks/             # Project task management
  tasks.json          # Current project tasks and status
  task_*.txt          # Detailed task specifications
```

### Development Conventions

#### Python Services (ingress, classifier, gateway)
- **FastAPI framework**: Async support, automatic OpenAPI docs
- **Pydantic models**: Type-safe data validation and serialization
- **ruff**: Code formatting and linting (replaces black, isort, flake8)
- **pytest**: Testing framework with async support
- **Dependency injection**: Use FastAPI's dependency system

#### Frontend (dashboard)
- **React 19**: Latest React with TypeScript
- **Vite**: Fast development server and build tool
- **ESLint**: Code linting with TypeScript rules
- **Component patterns**: Functional components with hooks
- **Type safety**: Strict TypeScript configuration

#### Database Patterns
- **PostgreSQL + pgvector**: Relational data with vector similarity
- **Migrations**: Schema changes via init-db.sql updates
- **Connection pooling**: Efficient database connections
- **Vector indexing**: Optimized similarity search performance

## Project Documentation

### Task and Feature Tracking
- **`/tasks/`** - Current implementation tasks with detailed specifications
- **`FUTURE_FEATURES.md`** - Comprehensive feature wishlist and long-term roadmap
- **`README_FEATURES_AUDIT.md`** - Analysis of README vs. actual implementation status

### Development References
- **`DEVELOPMENT.md`** - Comprehensive development environment guide
- **`README.md`** - Project overview and aspirational feature list
- **`CLAUDE.md`** - This file - architectural guidance for AI assistants

## Git Workflow

Follow conventional commit format as defined in project rules. The system uses standard Git workflows with feature branches and pull requests.

### Commit Strategy
- Make frequent, focused commits for logical units of work
- Use descriptive commit messages following conventional commit format
- Run `make lint` and `make test` before each commit
- Reference relevant issue or task numbers when applicable

## Project Optimization Tracking

- Remember to auto-update @docs/PERFORMANCE_OPTIMIZATION_TRACKER.md on-the-fly as new optimizations are made