# Auto-Triager Development Makefile
# Provides targets for development, testing, linting, and deployment

.PHONY: help dev dev-up dev-down dev-logs dev-clean test test-docker test-ingress test-classifier test-gateway test-dashboard test-classifier-docker test-gateway-docker test-dashboard-docker lint lint-python lint-js clean build deploy-fly setup-env check-env check-containers test-webhook-manual kafka-tail

# Default target
help: ## Show this help message
	@echo "Auto-Triager Development Commands"
	@echo "================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development Environment
dev: dev-up ## Start the complete development environment
	@echo "🚀 Development environment is starting..."
	@echo "📊 Dashboard will be available at: http://localhost:3000"
	@echo "🔗 API Gateway available at: http://localhost:8000"
	@echo "📥 Webhook Ingress available at: http://localhost:8001"
	@echo "🗄️  PostgreSQL available at: localhost:5432"
	@echo "📡 Redpanda Console available at: http://localhost:8080"
	@echo ""
	@echo "Use 'make dev-logs' to view logs or 'make dev-down' to stop"

dev-up: ## Start all development services
	@echo "Starting development environment..."
	cd infra && docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@make check-services

dev-down: ## Stop all development services
	@echo "Stopping development environment..."
	cd infra && docker compose down

dev-logs: ## View logs from all services
	cd infra && docker compose logs -f

dev-logs-service: ## View logs from specific service (usage: make dev-logs-service SERVICE=ingress)
	cd infra && docker compose logs -f $(SERVICE)

dev-restart: ## Restart development environment
	@make dev-down
	@make dev-up

dev-clean: ## Stop services and remove volumes/networks
	@echo "Cleaning development environment..."
	cd infra && docker compose down -v --remove-orphans
	@echo "Pruning unused Docker resources..."
	docker system prune -f

# Health Checks
check-services: ## Check if all services are healthy
	@echo "Checking service health..."
	@echo -n "PostgreSQL: "
	@docker exec auto-triager-postgres pg_isready -U postgres >/dev/null 2>&1 && echo "✅ Ready" || echo "❌ Not Ready"
	@echo -n "Redpanda: "
	@curl -s http://localhost:9644/v1/cluster/health >/dev/null 2>&1 && echo "✅ Ready" || echo "❌ Not Ready"

check-containers: ## Check if all containers are running
	@echo "Checking containers..."
	@echo -n "Ingress: "
	@docker ps --format "table {{.Names}}" | grep -q "auto-triager-ingress" && echo "✅ Running" || echo "❌ Not Running"
	@echo -n "Classifier: "
	@docker ps --format "table {{.Names}}" | grep -q "auto-triager-classifier" && echo "✅ Running" || echo "❌ Not Running"
	@echo -n "Gateway: "
	@docker ps --format "table {{.Names}}" | grep -q "auto-triager-gateway" && echo "✅ Running" || echo "❌ Not Running"
	@echo -n "Dashboard: "
	@docker ps --format "table {{.Names}}" | grep -q "auto-triager-dashboard" && echo "✅ Running" || echo "❌ Not Running"

# Testing
test: ## Run all tests
	@echo "Running all tests..."
	@make test-ingress
	@make test-classifier
	@make test-gateway
	@make test-dashboard

test-docker: ## Run all tests in Docker containers (requires dev environment)
	@echo "Running all tests in Docker containers..."
	@make check-containers
	@make test-ingress
	@make test-classifier-docker
	@make test-gateway-docker
	@make test-dashboard-docker

test-ingress: ## Run ingress component tests
	@echo "Testing ingress component..."
	@if docker ps --format "table {{.Names}}" | grep -q "auto-triager-ingress"; then \
		echo "Running tests in Docker container..."; \
		docker exec auto-triager-ingress python -m pytest test_webhook.py -v; \
	else \
		echo "❌ Ingress container not running. Start with 'make dev' first"; \
		exit 1; \
	fi

test-classifier: ## Run classifier component tests (local)
	@echo "Testing classifier component locally..."
	@if [ -f classifier/requirements.txt ]; then \
		cd classifier && python -m pytest tests/ -v; \
	else \
		echo "⚠️  Classifier tests not yet implemented"; \
	fi

test-classifier-docker: ## Run classifier component tests in Docker
	@echo "Testing classifier component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "auto-triager-classifier"; then \
		if docker exec auto-triager-classifier find . -name "test*.py" -o -name "*test.py" | grep -q .; then \
			docker exec auto-triager-classifier python -m pytest -v; \
		else \
			echo "⚠️  No test files found in classifier container"; \
		fi; \
	else \
		echo "❌ Classifier container not running. Start with 'make dev' first"; \
	fi

test-gateway: ## Run gateway component tests (local)
	@echo "Testing gateway component locally..."
	@if [ -f gateway/requirements.txt ]; then \
		cd gateway && python -m pytest tests/ -v; \
	else \
		echo "⚠️  Gateway tests not yet implemented"; \
	fi

test-gateway-docker: ## Run gateway component tests in Docker
	@echo "Testing gateway component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "auto-triager-gateway"; then \
		if docker exec auto-triager-gateway find . -name "test*.py" -o -name "*test.py" | grep -q .; then \
			docker exec auto-triager-gateway python -m pytest -v; \
		else \
			echo "⚠️  No test files found in gateway container"; \
		fi; \
	else \
		echo "❌ Gateway container not running. Start with 'make dev' first"; \
	fi

test-dashboard: ## Run dashboard component tests (local)
	@echo "Testing dashboard component locally..."
	@if [ -f dashboard/package.json ]; then \
		cd dashboard && npm test; \
	else \
		echo "⚠️  Dashboard tests not yet implemented"; \
	fi

test-dashboard-docker: ## Run dashboard component tests in Docker
	@echo "Testing dashboard component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "auto-triager-dashboard"; then \
		if docker exec auto-triager-dashboard test -f package.json; then \
			docker exec auto-triager-dashboard npm test; \
		else \
			echo "⚠️  No package.json found in dashboard container"; \
		fi; \
	else \
		echo "❌ Dashboard container not running. Start with 'make dev' first"; \
	fi

test-webhook-manual: ## Run manual webhook testing script
	@echo "Running manual webhook tests..."
	@if [ -f scripts/test-webhook-manual.sh ]; then \
		./scripts/test-webhook-manual.sh; \
	else \
		echo "❌ Manual test script not found at scripts/test-webhook-manual.sh"; \
	fi

# Linting
lint: ## Run all linters
	@echo "Running all linters..."
	@make lint-python
	@make lint-js

lint-python: ## Run Python linters (ruff)
	@echo "Linting Python code..."
	@for dir in ingress classifier gateway; do \
		if [ -f $$dir/requirements.txt ]; then \
			echo "Linting $$dir..."; \
			cd $$dir && ruff check . && ruff format --check .; \
			cd ..; \
		else \
			echo "⚠️  $$dir not yet set up for linting"; \
		fi; \
	done

lint-js: ## Run JavaScript/TypeScript linters
	@echo "Linting JavaScript/TypeScript code..."
	@if [ -f dashboard/package.json ]; then \
		cd dashboard && npm run lint; \
	else \
		echo "⚠️  Dashboard not set up for linting yet"; \
	fi

lint-fix: ## Fix linting issues automatically
	@echo "Fixing linting issues..."
	@for dir in ingress classifier gateway; do \
		if [ -f $$dir/requirements.txt ]; then \
			echo "Fixing $$dir..."; \
			cd $$dir && ruff check --fix . && ruff format .; \
			cd ..; \
		fi; \
	done
	@if [ -f dashboard/package.json ]; then \
		cd dashboard && npm run lint:fix; \
	fi

# Building
build: ## Build all Docker images
	@echo "Building all Docker images..."
	cd infra && docker compose build

build-service: ## Build specific service (usage: make build-service SERVICE=ingress)
	@echo "Building $(SERVICE) service..."
	cd infra && docker compose build $(SERVICE)

# Database Management
db-reset: ## Reset the database with fresh schema
	@echo "Resetting database..."
	@make dev-down
	cd infra && docker volume rm infra_postgres_data 2>/dev/null || true
	@make dev-up
	@echo "Database reset complete"

db-shell: ## Open PostgreSQL shell
	@echo "Opening PostgreSQL shell..."
	@if [ -t 0 ]; then \
		docker exec -it auto-triager-postgres psql -U postgres -d auto_triager; \
	else \
		echo "❌ No TTY available. Use 'make db-query SQL=\"SELECT * FROM auto_triager.issues;\"' instead"; \
		echo "Or run directly: docker exec -it auto-triager-postgres psql -U postgres -d auto_triager"; \
	fi

db-query: ## Run SQL query (usage: make db-query SQL="SELECT * FROM auto_triager.issues;")
	@if [ -z "$(SQL)" ]; then \
		echo "❌ Usage: make db-query SQL=\"SELECT * FROM auto_triager.issues;\""; \
		echo "Examples:"; \
		echo "  make db-query SQL=\"SELECT * FROM auto_triager.issues;\""; \
		echo "  make db-query SQL=\"SELECT COUNT(*) FROM auto_triager.enriched_issues;\""; \
		echo "  make db-query SQL=\"\\dt auto_triager.*\""; \
	else \
		docker exec auto-triager-postgres psql -U postgres -d auto_triager -c "$(SQL)"; \
	fi

db-tables: ## List all tables in the database
	@echo "Tables in auto_triager schema:"
	@docker exec auto-triager-postgres psql -U postgres -d auto_triager -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'auto_triager' ORDER BY table_name;"

db-issues: ## Show all issues in the database
	@echo "Issues in database:"
	@docker exec auto-triager-postgres psql -U postgres -d auto_triager -c "SELECT id, issue_number, title, author, author_association, created_at FROM auto_triager.issues ORDER BY created_at DESC;"

db-enriched: ## Show enriched issues in the database
	@echo "Enriched issues in database:"
	@docker exec auto-triager-postgres psql -U postgres -d auto_triager -c "SELECT id, issue_id, category, priority, confidence_score, processed_at FROM auto_triager.enriched_issues ORDER BY processed_at DESC;"

db-backup: ## Backup the database
	@echo "Creating database backup..."
	docker exec auto-triager-postgres pg_dump -U postgres auto_triager > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Backup created: backup_$(shell date +%Y%m%d_%H%M%S).sql"

# Kafka/Redpanda Management
kafka-topics: ## List Kafka topics
	docker exec auto-triager-redpanda rpk topic list

kafka-create-topics: ## Create required Kafka topics
	@echo "Creating Kafka topics..."
	docker exec auto-triager-redpanda rpk topic create issues.raw --partitions 3 --replicas 1
	docker exec auto-triager-redpanda rpk topic create issues.enriched --partitions 3 --replicas 1
	@echo "Topics created successfully"

kafka-console: ## Consume recent messages from Kafka topic (usage: make kafka-console TOPIC=issues.raw)
	docker exec auto-triager-redpanda rpk topic consume $(TOPIC) --num 10 --offset start

kafka-tail: ## Tail Kafka topic messages interactively (usage: make kafka-tail TOPIC=issues.raw)
	@echo "Tailing messages from topic: $(TOPIC)"
	@echo "Press Ctrl+C to stop"
	docker exec -it auto-triager-redpanda rpk topic consume $(TOPIC) --follow

# Environment Setup
setup-env: ## Set up development environment files
	@echo "Setting up environment files..."
	@if [ ! -f .env ]; then \
		echo "Creating .env file from template..."; \
		cp .env.example .env 2>/dev/null || echo "# Auto-Triager Environment Variables" > .env; \
		echo "POSTGRES_URL=postgresql://postgres:password@localhost:5432/auto_triager" >> .env; \
		echo "KAFKA_BOOTSTRAP_SERVERS=localhost:9092" >> .env; \
		echo "OPENAI_API_KEY=your_openai_api_key_here" >> .env; \
		echo "⚠️  Please update .env with your actual API keys"; \
	else \
		echo ".env file already exists"; \
	fi

check-env: ## Check environment setup
	@echo "Checking environment setup..."
	@if [ -f .env ]; then \
		echo "✅ .env file exists"; \
		echo "Environment variables:"; \
		grep -E '^[A-Z_]+=.*' .env | sed 's/=.*/=***/' || true; \
	else \
		echo "❌ .env file missing - run 'make setup-env'"; \
	fi

# Deployment
deploy-fly: ## Deploy to Fly.io
	@echo "Deploying to Fly.io..."
	@if ! command -v flyctl >/dev/null 2>&1; then \
		echo "❌ flyctl not found. Please install Fly CLI first:"; \
		echo "   https://fly.io/docs/getting-started/installing-flyctl/"; \
		exit 1; \
	fi
	@echo "🚀 Starting Fly.io deployment..."
	flyctl deploy

# Utility
clean: ## Clean up development environment and Docker resources
	@make dev-clean
	@echo "Cleaning up Docker images..."
	docker image prune -f

logs: ## Alias for dev-logs
	@make dev-logs

status: ## Show status of all services
	@echo "Development Environment Status"
	@echo "============================="
	cd infra && docker compose ps
	@echo ""
	@make check-services

install-deps: ## Install development dependencies
	@echo "Installing development dependencies..."
	@command -v ruff >/dev/null 2>&1 || (echo "Installing ruff..." && pip install ruff)
	@command -v docker >/dev/null 2>&1 || (echo "❌ Docker not found. Please install Docker first." && exit 1)
	@command -v docker compose >/dev/null 2>&1 || (echo "❌ Docker Compose not found. Please install Docker Compose first." && exit 1)
	@echo "✅ Dependencies check complete"

# Development shortcuts
shell-ingress: ## Open shell in ingress container
	docker exec -it auto-triager-ingress /bin/bash

shell-classifier: ## Open shell in classifier container
	docker exec -it auto-triager-classifier /bin/bash

shell-gateway: ## Open shell in gateway container
	docker exec -it auto-triager-gateway /bin/bash

shell-dashboard: ## Open shell in dashboard container
	docker exec -it auto-triager-dashboard /bin/bash
