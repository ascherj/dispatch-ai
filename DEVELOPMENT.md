# Auto-Triager Development Environment

This guide provides everything you need to start developing on Auto-Triager with a seamless Docker Compose setup.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Git
- Make (for convenience commands)

### One-Command Startup
```bash
# Clone and start the entire development environment
git clone <your-repo-url>
cd auto-triager
make dev
```

That's it! The entire development environment will start automatically.

## 📋 Environment Details

### Services Overview
After running `make dev`, you'll have these services running:

| Service | Port | Description | URL |
|---------|------|-------------|-----|
| **Ingress** | 8000 | FastAPI webhook receiver | http://localhost:8000 |
| **Gateway** | 8002 | WebSocket/REST API | http://localhost:8002 |
| **Dashboard** | 3000 | React frontend (Vite) | http://localhost:3000 |
| **PostgreSQL** | 5432 | Database with pgvector | localhost:5432 |
| **Redpanda** | 19092 | Kafka-compatible message broker | localhost:19092 |

### Key URLs
- 🎯 **Main Dashboard**: http://localhost:3000
- 📚 **API Documentation**: http://localhost:8002/docs
- 🪝 **GitHub Webhook**: http://localhost:8000/webhook/github
- 💾 **Database**: postgresql://postgres:postgres@localhost:5432/auto_triager

## 🛠️ Development Commands

### Essential Commands
```bash
# Start all services
make dev

# Check service status
make status

# View logs from all services
make dev-logs

# Stop all services
make dev-down

# Restart services
make dev-restart

# Test environment health
./scripts/test-dev-environment.sh
```

### Database Commands
```bash
# Access database shell
make db-shell

# Reset database (recreate with fresh schema)
make db-reset

# Backup database
make db-backup
```

### Kafka/Redpanda Commands
```bash
# List Kafka topics
make kafka-topics

# Create required topics
make kafka-create-topics

# Access Kafka console
make kafka-console
```

### Individual Service Commands
```bash
# Access service shells
make shell-ingress
make shell-classifier
make shell-gateway
make shell-dashboard

# Build specific service
make build-service SERVICE=gateway

# View logs for specific service
docker logs auto-triager-gateway -f
```

## 🔧 Configuration

### Environment Variables
The development environment uses a `.env` file for configuration. Key variables:

```bash
# Database
POSTGRES_DB=auto_triager
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# API Keys (replace with your actual keys)
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
GITHUB_WEBHOOK_SECRET=your-webhook-secret-here

# Service URLs (automatically configured for Docker)
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/auto_triager
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092
```

### Development Features
- **🔄 Hot Reload**: All services support hot reloading
  - Python services: Volume-mounted with `--reload`
  - React dashboard: Vite dev server with HMR
- **📦 Volume Mounts**: Source code is mounted for live editing
- **🔍 Health Checks**: All services have health endpoints
- **🌐 Networking**: Services communicate via Docker network

## 🧩 Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Dashboard     │    │    Gateway      │    │    Ingress      │
│   (React/Vite)  │◄──►│ (WebSocket/API) │    │   (Webhooks)    │
│   Port: 3000    │    │   Port: 8002    │    │   Port: 8000    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Classifier    │    │   PostgreSQL    │    │    Redpanda     │
│  (LangChain/AI) │◄──►│   + pgvector    │◄──►│     (Kafka)     │
│   Port: 8001    │    │   Port: 5432    │    │   Port: 19092   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚦 Development Workflow

### 1. Starting Development
```bash
# Start everything
make dev

# Verify all services are healthy
make status
./scripts/test-dev-environment.sh
```

### 2. Making Changes
- **Frontend**: Edit files in `dashboard/src/` - changes auto-reload
- **Backend**: Edit files in `gateway/`, `ingress/`, `classifier/` - changes auto-reload
- **Database**: Use `make db-shell` for direct access

### 3. Testing
```bash
# Run linters
make lint

# Run tests
make test

# Test environment health
./scripts/test-dev-environment.sh
```

### 4. Debugging
```bash
# View logs
make dev-logs

# Access service shell
make shell-gateway

# Check service health
curl http://localhost:8002/health
```

## 🔍 Troubleshooting

### Common Issues

#### Services Won't Start
```bash
# Check Docker is running
docker ps

# Rebuild containers
make dev-down
make dev

# Check logs for errors
make dev-logs
```

#### Port Conflicts
If you get port binding errors:
```bash
# Check what's using the ports
lsof -i :3000 -i :8000 -i :8002 -i :5432 -i :19092

# Stop conflicting services or change ports in docker-compose.yml
```

#### Database Issues
```bash
# Reset database
make db-reset

# Check database is accessible
make db-shell
```

#### Dependency Conflicts
```bash
# Rebuild with fresh dependencies
make dev-down
docker system prune -f
make dev
```

### Health Checks
All services expose health endpoints:
- Ingress: http://localhost:8000/health
- Gateway: http://localhost:8002/health
- Dashboard: http://localhost:3000 (HTML response)

### Log Locations
```bash
# All services
make dev-logs

# Individual services
docker logs auto-triager-ingress -f
docker logs auto-triager-gateway -f
docker logs auto-triager-classifier -f
docker logs auto-triager-dashboard -f
```

## 📝 Development Tips

### Hot Reloading
- **Python**: FastAPI services auto-reload on file changes
- **React**: Vite provides instant HMR (Hot Module Replacement)
- **Database**: Schema changes require `make db-reset`

### Real-time Features
- WebSocket connection: ws://localhost:8002/ws
- Live dashboard updates when issues are classified
- Real-time message broadcasting to connected clients

### Testing APIs
```bash
# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:8002/health

# Test API endpoints
curl http://localhost:8002/api/issues
curl http://localhost:8002/api/stats

# Test WebSocket (if websocat installed)
echo "hello" | websocat ws://localhost:8002/ws
```

### Database Development
```bash
# Connect to database
make db-shell

# Common queries
\dt                           # List tables
SELECT * FROM issues LIMIT 5; # View sample data
\d issues                     # Describe table structure
```

## 🎯 Next Steps

Once your development environment is running:

1. **Visit the Dashboard**: http://localhost:3000
2. **Explore API Docs**: http://localhost:8002/docs
3. **Start implementing features** from the task list
4. **Test with real GitHub webhooks** (use ngrok for local testing)

## 🤝 Contributing

When making changes:
1. Ensure all services pass health checks
2. Run `make lint` and `make test`
3. Test the full flow with `./scripts/test-dev-environment.sh`
4. Document any new environment variables or setup steps

---

**Happy coding! 🚀**
