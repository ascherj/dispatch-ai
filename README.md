# Auto-Triager 🚀

> **Enterprise-grade intelligent GitHub issue classification and triaging system**  
> Transform chaotic issue queues into organized, AI-enhanced workflows with real-time processing and human oversight.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

## 🎯 The Problem

GitHub repositories receive **hundreds or thousands of issues** that require manual triaging—a time-consuming, inconsistent process that creates bottlenecks and frustration for development teams.

## 💡 The Solution

Auto-Triager provides **intelligent, real-time issue classification** using AI while maintaining human oversight and continuous learning capabilities.

### Key Benefits
- **⚡ Real-time Processing**: Issues classified within seconds of creation
- **🎯 AI-Powered Intelligence**: LangChain + OpenAI for sophisticated analysis
- **👥 Human-in-the-Loop**: Manual review and feedback improves accuracy
- **📊 Vector Similarity**: Find related issues and detect patterns
- **🔄 Continuous Learning**: Feedback loop enhances AI performance over time

## 🏗️ System Architecture

Auto-Triager implements a **microservices architecture** designed for enterprise-scale performance:

```
GitHub Issues → Ingress → Kafka → AI Classifier → Database → Gateway → Dashboard
                  ↓           ↓         ↓           ↓         ↓        ↓
              Webhooks    Raw Events  Enhanced   Vector    API    Real-time UI
              Security    Streaming   Analysis   Storage   Layer   Human Review
```

### Core Services

#### 🚪 **Ingress Service** (Port 8000)
- **FastAPI webhook receiver** with GitHub signature validation
- **Rate limiting** and security hardening
- **Event streaming** to Kafka message queue

#### 🧠 **Classifier Service** (Background Worker)
- **LangChain integration** for prompt engineering
- **OpenAI GPT-4** for intelligent issue analysis
- **Vector embeddings** for similarity detection
- **Batch processing** with error recovery

#### 🌐 **Gateway Service** (Port 8002)
- **WebSocket real-time updates** for live dashboard
- **REST API** for issue queries and manual corrections
- **Authentication & authorization** for secure access

#### 📊 **Dashboard** (Port 3000)
- **React TypeScript** frontend with real-time updates
- **Interactive correction interface** for human feedback
- **Analytics and reporting** on classification accuracy
- **Issue clustering visualization** and pattern detection

## 🛠️ Technology Stack

### Backend & AI
- **FastAPI** - High-performance async Python framework
- **LangChain** - Advanced AI prompt engineering and model abstraction
- **OpenAI GPT-4** - State-of-the-art language model for classification
- **PostgreSQL 16** with **pgvector** - Vector similarity search at scale

### Infrastructure & Messaging
- **Redpanda** - Kafka-compatible streaming platform (1M+ msgs/sec)
- **Docker Compose** - Containerized development and deployment
- **Fly.io** - Global edge deployment platform
- **Prometheus + Grafana** - Production monitoring and alerting

### Frontend & Real-time
- **React 19** with **TypeScript** - Type-safe, modern UI framework
- **WebSocket** - Real-time bidirectional communication
- **Vite** - Lightning-fast development and build tooling

## 🚀 Performance Specifications

| Metric | Target | Technology |
|--------|--------|------------|
| **Throughput** | 1,000+ issues/minute | Kafka + async processing |
| **Latency** | <5 seconds end-to-end | Optimized AI pipeline |
| **Accuracy** | 90%+ classification | Human-in-the-loop feedback |
| **Uptime** | 99.9% availability | Microservices + health checks |
| **Scaling** | Horizontal auto-scaling | Stateless service design |

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
git clone https://github.com/your-org/auto-triager.git
cd auto-triager

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
make deploy-fly
```

## 🔧 Development Guide

### Environment Configuration
```bash
# Required API keys (add to .env file)
OPENAI_API_KEY=your_openai_key_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Database and messaging (auto-configured for development)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/auto_triager
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
```

### Service Development
Each microservice supports **hot reload** for rapid development:

```bash
# Edit Python services (ingress, classifier, gateway)
# Changes automatically reload via volume mounts

# Edit React dashboard  
# Vite provides instant HMR (Hot Module Replacement)

# Database schema changes
make db-reset  # Recreates with fresh schema
```

### Testing Strategy
- **Unit Tests**: Individual function testing (`pytest`, `vitest`)
- **Integration Tests**: Service-to-service communication
- **End-to-End Tests**: Complete workflow validation
- **Load Tests**: Performance under high throughput

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

## 🚀 Deployment & Production

### Fly.io Global Deployment
```bash
# Deploy to production with zero-downtime
make deploy-fly

# Scale services independently
flyctl scale count web=3 worker=5

# Monitor production metrics
flyctl logs -a auto-triager-production
```

### Infrastructure as Code
- **Docker multi-stage builds** for optimized production images
- **Health checks** for all services with automatic restart
- **Environment-specific configurations** for dev/staging/prod
- **Horizontal scaling** support with stateless service design

## 📊 Monitoring & Observability

### Production Metrics
- **Classification accuracy** tracking over time
- **Processing latency** percentiles and SLA monitoring  
- **Throughput metrics** for capacity planning
- **Error rates** and failure mode analysis

### Health Dashboards
- **Service status** monitoring across all microservices
- **Database performance** including vector similarity queries
- **Kafka lag** and message processing rates
- **WebSocket connection** health and real-time update delivery

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Development Setup
1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/your-username/auto-triager.git`
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

- **🐛 Bug Reports**: [GitHub Issues](https://github.com/your-org/auto-triager/issues)
- **💡 Feature Requests**: [GitHub Discussions](https://github.com/your-org/auto-triager/discussions)
- **📖 Documentation**: [Full Developer Guide](./docs/DEVELOPMENT.md)
- **🔧 Configuration Help**: [CLAUDE.md](./CLAUDE.md) - AI Assistant Guidelines

---

**Built with ❤️ for the developer community**  
*Transform your GitHub workflow from reactive to proactive with intelligent automation.*
