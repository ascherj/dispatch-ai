# DispatchAI 🚀

> **Enterprise-grade intelligent GitHub issue classification and triaging system**
> Transform chaotic issue queues into organized, AI-enhanced workflows with real-time processing and human oversight.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

## 🎯 The Problem

GitHub repositories receive **hundreds or thousands of issues** that require manual triaging—a time-consuming, inconsistent process that creates bottlenecks and frustration for development teams.

## 💡 The Solution

DispatchAI automates GitHub issue classification using **event-driven architecture** and **AI integration** while maintaining human oversight and continuous learning capabilities.

![DispatchAI Dashboard](screenshot.png)
*Real-time dashboard showing live issue classification with AI analysis, statistics, and manual correction capabilities*

### Technical Approach
- **⚡ Event-Driven Architecture**: Kafka-based async processing prevents webhook timeouts
- **🎯 AI Integration**: OpenAI GPT-4o-mini with circuit breaker patterns for reliability
- **👥 Human-in-the-Loop**: Manual correction system for continuous improvement
- **📊 Vector Similarity**: PostgreSQL pgvector for semantic issue clustering
- **🔄 Real-Time Updates**: WebSocket broadcasting for instant dashboard updates

## 🏗️ System Architecture

DispatchAI implements a **microservices architecture** designed for enterprise-scale performance:

```
GitHub Issues → Ingress → Kafka → AI Classifier → Database → Gateway → Dashboard
                  ↓           ↓         ↓           ↓         ↓        ↓
              Webhooks    Raw Events  Enhanced   Vector    API    Real-time UI
              Security    Streaming   Analysis   Storage   Layer   Human Review
```

### Core Services

#### 🚪 **Ingress Service** (Port 8000) - Webhook Processing
- **Async FastAPI** with GitHub signature validation (HMAC-SHA256)
- **Rate limiting** with sliding window algorithm (100 req/min per IP)
- **Non-blocking Kafka publishing** for immediate webhook response

#### 🧠 **Classifier Service** - AI Processing Worker
- **LangChain + OpenAI GPT-4o-mini** integration with structured prompts
- **Vector embeddings** using text-embedding-3-small (1536 dimensions)
- **Circuit breaker pattern** with fallback classification for reliability
- **Kafka consumer** with automatic retry and dead letter queue

#### 🌐 **Gateway Service** (Port 8002) - API & Real-Time Hub
- **FastAPI with WebSocket support** for real-time dashboard updates
- **Connection manager** with automatic cleanup of disconnected clients
- **REST endpoints** for issue queries, stats, and manual corrections
- **Kafka consumer** for broadcasting classification results

#### 📊 **Dashboard** (Port 3000) - React Frontend
- **React 19 + TypeScript** with strict type checking
- **WebSocket integration** with automatic reconnection and exponential backoff
- **Real-time issue updates** and interactive correction interface
- **Responsive design** with modern CSS and component architecture

## 🛠️ Technology Stack

### Backend & AI
- **FastAPI** - Async Python framework with automatic OpenAPI documentation
- **LangChain** - AI prompt engineering with structured output parsing
- **OpenAI GPT-4o-mini** - Cost-optimized model (65% cheaper than GPT-3.5-turbo)
- **PostgreSQL 16** with **pgvector** - Vector similarity search and ACID compliance

### Infrastructure & Messaging
- **Redpanda** - Kafka-compatible event streaming with compression support
- **Docker Compose** - Multi-service containerization with health checks
- **Cloud Deployment** - VPS and container platform ready
- **Monitoring** - Structured logging with JSON output for observability

### Frontend & Real-time
- **React 19** with **TypeScript** - Strict typing with modern React features
- **WebSocket** - Bidirectional real-time communication with connection management
- **Vite** - Fast build tool with hot module replacement (HMR)

## 🏗️ Technical Architecture Highlights

### Event-Driven Design for Scale
```python
# Non-blocking webhook processing prevents GitHub timeouts
@app.post("/webhook/github")
async def github_webhook(request: Request):
    # Fast validation and immediate response (<100ms target)
    signature_valid = await validate_github_signature(request)
    await kafka_producer.send("issues.raw", webhook_data)
    return {"status": "accepted"}  # GitHub gets immediate response
```

### AI Integration with Graceful Degradation
```python
# Circuit breaker pattern for AI service reliability
async def classify_with_fallback(issue_data):
    try:
        result = await openai_client.create_completion(prompt)
        return parse_ai_response(result)
    except (APIError, RateLimitError) as e:
        logger.warning(f"AI service unavailable: {e}")
        return fallback_classification(issue_data)  # Keyword-based backup
```

### Real-Time WebSocket Broadcasting
```python
# Connection management with automatic cleanup
class ConnectionManager:
    async def broadcast_update(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except WebSocketDisconnect:
                disconnected.append(connection)
        # Clean up failed connections
        for conn in disconnected:
            self.active_connections.remove(conn)
```

### Vector Similarity with PostgreSQL + pgvector
```sql
-- Semantic similarity search for related issues
SELECT title, category, 1 - (embedding <-> %s::vector) as similarity
FROM dispatchai.enriched_issues
WHERE 1 - (embedding <-> %s::vector) > 0.7
ORDER BY embedding <-> %s::vector LIMIT 5;
```

## 📈 Data Flow & Processing

### 1. **GitHub Event Capture**
```json
{
  "action": "opened",
  "issue": {
    "title": "App crashes on startup",
    "body": "When I run npm start, I get error XYZ...",
    "labels": [], "assignees": []
  }
}
```

### 2. **AI Enhancement & Classification**
```json
{
  "original_issue": { /* GitHub data */ },
  "ai_analysis": {
    "category": "bug",
    "priority": "high",
    "tags": ["startup", "crash", "npm"],
    "similar_issues": [123, 456, 789],
    "estimated_effort": "medium",
    "suggested_assignee": "backend-team",
    "confidence_score": 0.94
  }
}
```

### 3. **Real-time Dashboard Updates**
- Live WebSocket notifications to connected browsers
- Interactive approval/correction interface
- Pattern recognition and clustering visualization

## ⚡ Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for dashboard development)
- Python 3.11+ (for service development)

### One-Command Development Setup
```bash
# Clone and start the entire system
git clone https://github.com/your-org/dispatch-ai.git
cd dispatch-ai

# Start all services with hot reload
make dev
```

**That's it!** 🎉 The complete development environment starts automatically:

| Service | URL | Description |
|---------|-----|-------------|
| 📊 **Dashboard** | http://localhost:3000 | React UI with real-time updates |
| 🔌 **API Gateway** | http://localhost:8002 | REST API + WebSocket endpoint |
| 📥 **Webhook Receiver** | http://localhost:8000 | GitHub webhook ingress |
| 🗄️ **Database** | localhost:5432 | PostgreSQL with pgvector |
| 📡 **Message Queue** | localhost:19092 | Redpanda console |

### Development Commands
```bash
# Health check all services
make status

# View logs from all services
make dev-logs

# Run comprehensive tests
make test

# Lint all code (Python + TypeScript)
make lint

# Reset database with fresh schema
make db-reset

# Deploy to production
./scripts/start-prod.sh
```

## 🔧 Development Guide

### Environment Configuration
```bash
# Required API keys (add to .env file)
OPENAI_API_KEY=your_openai_key_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Database and messaging (auto-configured for development)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dispatchai
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
```

### Development Workflow
```bash
# Hot reload development - all services restart automatically on code changes
make dev        # Start complete environment with volume mounts
make dev-logs   # Stream logs from all services
make db-shell   # Direct PostgreSQL access for debugging
make kafka-console TOPIC=issues.raw  # Debug Kafka message flow
```

### Test Script Setup

For end-to-end testing, create a virtual environment at the project root:

```bash
# One-time setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests (from project root)
./scripts/send_webhook.sh              # Full webhook pipeline test
./scripts/test-correlation-tracing.sh  # Distributed tracing verification
```

### Code Quality & Testing
```bash
# Comprehensive linting (Python + TypeScript)
make lint       # ruff (Python) + ESLint (TypeScript)
make lint-fix   # Auto-fix formatting issues

# Multi-layer testing strategy
make test       # Unit tests (pytest + vitest)
make test-webhook  # Integration tests with real HTTP requests
```

### Production-Ready Features
- **Health Checks**: All services expose `/health` endpoints
- **Graceful Shutdown**: Proper cleanup of connections and consumers
- **Error Recovery**: Circuit breakers, retries, and fallback mechanisms
- **Observability**: Structured logging with request tracing

## 🎯 Use Cases & Applications

### Enterprise Teams
- **Large repositories** with 100+ issues per day
- **Multiple maintainers** needing consistent triaging
- **Complex projects** requiring specialized expertise routing

### Open Source Projects
- **Community-driven** repositories with diverse contributors
- **Automated first-response** to reduce maintainer burden
- **Pattern detection** for common issues and feature requests

### SaaS Companies
- **Customer support** integration via GitHub issues
- **Bug tracking** with automatic severity assessment
- **Feature request** classification and prioritization

## 🏆 Key Features in Detail

### 🤖 **Intelligent Classification**
- **Multi-dimensional analysis**: Category, priority, effort estimation, team assignment
- **Context-aware processing**: Considers repository history and patterns
- **Confidence scoring**: Transparency in AI decision-making

### 🔄 **Continuous Learning**
- **Human feedback loop**: Manual corrections improve future accuracy
- **Pattern recognition**: Learns repository-specific conventions
- **Model fine-tuning**: Adapts to project-specific terminology

### ⚡ **Real-time Performance**
- **Sub-5-second processing**: From GitHub webhook to classification
- **Live dashboard updates**: WebSocket-powered real-time UI
- **Batch processing capability**: Handle traffic spikes gracefully

### 🔒 **Enterprise Security**
- **GitHub signature validation**: Cryptographic webhook verification
- **Rate limiting**: Protection against abuse and DoS attacks
- **Audit logging**: Complete trail of all classifications and corrections

## 🚀 Production Deployment

### Docker Compose Deployment
```bash
# Local production testing
docker-compose -f docker-compose.prod.yml up -d

# Cloud VPS deployment
./scripts/start-prod.sh  # Full production stack with monitoring
```

### Production-Ready Architecture
- **Multi-stage Docker builds** - Optimized images with security scanning
- **Health monitoring** - Comprehensive health checks with auto-restart
- **Zero-downtime deployments** - Rolling updates with fallback capability
- **Environment isolation** - Separate configs for dev/staging/prod
- **Horizontal scaling** - Stateless services with load balancing support

## 📊 Monitoring & Observability

### Built-in Monitoring Features
```python
# Structured logging with correlation IDs
logger.info("Issue classified",
           issue_id=issue.id,
           category=result.category,
           confidence=result.confidence,
           processing_time_ms=duration)

# Health check endpoints for all services
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_db_connection(),
        "kafka": await check_kafka_connection(),
        "ai_service": await check_openai_api()
    }
```

### Production Monitoring Strategy
- **Service health checks** - Database, Kafka, and AI service connectivity
- **Request tracing** - End-to-end request flow tracking
- **Error aggregation** - Structured logging for debugging and alerts
- **Resource monitoring** - CPU, memory, and connection pool usage
- **Business metrics** - Classification accuracy and processing volume

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Development Setup
1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/your-username/dispatch-ai.git`
3. **Start environment**: `make dev`
4. **Run tests**: `make test`

### Contribution Guidelines
- **Follow conventional commits**: `feat:`, `fix:`, `docs:`, etc.
- **Add tests** for new functionality
- **Update documentation** for user-facing changes
- **Run linting**: `make lint` before submitting

### Areas for Contribution
- 🔌 **New AI models**: Integration with additional LLMs
- 📊 **Analytics features**: Enhanced reporting and insights
- 🔒 **Security improvements**: Additional hardening measures
- 🎨 **UI/UX enhancements**: Dashboard improvements and new visualizations

## 📞 Support & Community

- **🐛 Bug Reports**: [GitHub Issues](https://github.com/your-org/dispatch-ai/issues)
- **💡 Feature Requests**: [GitHub Discussions](https://github.com/your-org/dispatch-ai/discussions)
- **📖 Documentation**: [Full Developer Guide](./docs/DEVELOPMENT.md)
- **🔧 Configuration Help**: [CLAUDE.md](./CLAUDE.md) - AI Assistant Guidelines
