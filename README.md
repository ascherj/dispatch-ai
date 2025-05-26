# Auto-Triager

An intelligent GitHub issue classification and triaging system that automatically processes, enriches, and categorizes GitHub issues using AI-powered analysis.

## Overview

Auto-Triager is a real-time system that:
- Receives GitHub webhook events for issues and pull requests
- Uses LangChain and OpenAI to classify and enrich issues with metadata
- Provides a real-time dashboard for monitoring and manual corrections
- Stores enriched data with vector embeddings for similarity analysis
- Supports manual feedback loops to improve AI accuracy

## Architecture

The system consists of several microservices:

- **Ingress Service** (`/ingress`) - FastAPI webhook receiver for GitHub events
- **Classifier Service** (`/classifier`) - LangChain-powered AI worker for issue analysis
- **Gateway Service** (`/gateway`) - WebSocket/REST API for real-time updates
- **Dashboard** (`/dashboard`) - React frontend for monitoring and corrections
- **Infrastructure** (`/infra`) - Docker Compose and deployment configurations

## Tech Stack

- **Backend**: FastAPI, LangChain, OpenAI API
- **Database**: PostgreSQL 16 with pgvector extension
- **Message Queue**: Redpanda (Kafka-compatible)
- **Frontend**: React with WebSocket support
- **Deployment**: Fly.io with Docker containers
- **Monitoring**: Prometheus, Loki, Grafana

## Performance Requirements

- Handle 1,000+ GitHub issues per minute
- Real-time processing and dashboard updates
- Vector similarity search for issue clustering
- Horizontal scaling support

## Quick Start

```bash
# Start local development environment
make dev

# Run tests
make test

# Run linters
make lint

# Deploy to production
make deploy-fly
```

## Development

See individual component READMEs for detailed setup instructions:
- [Ingress Service](./ingress/README.md)
- [Classifier Service](./classifier/README.md)
- [Gateway Service](./gateway/README.md)
- [Dashboard](./dashboard/README.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

For questions or issues, please open a GitHub issue or contact the maintainers.
