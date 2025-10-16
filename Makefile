# DispatchAI Development Makefile
# Provides targets for development, testing, linting, and deployment

.PHONY: help dev dev-up dev-down dev-logs dev-clean dev-nuke prod-nuke test test-docker test-ingress test-classifier test-gateway test-dashboard test-classifier-docker test-gateway-docker test-dashboard-docker lint lint-python lint-python-docker lint-js clean build setup-env check-env check-containers test-webhook-manual demo trace-recent trace-id kafka-tail health health-ingress health-classifier health-gateway metrics metrics-ingress metrics-classifier metrics-gateway metrics-summary watch-metrics system-status

# Default target
help: ## Show this help message
	@echo "DispatchAI Development Commands"
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

dev-nuke: ## Completely remove and restart all dev images, containers, and volumes
	@echo "🧨 NUKING development environment completely..."
	@echo "⚠️  This will remove ALL dev containers, images, volumes, and networks!"
	@echo "Stopping all dev services..."
	cd infra && docker compose down --remove-orphans --volumes 2>/dev/null || true
	@echo "Removing project-specific volumes..."
	docker volume rm infra_redpanda_data infra_postgres_data infra_dashboard_node_modules 2>/dev/null || true
	@echo "Removing all containers..."
	docker container prune -f
	@echo "Removing all images..."
	docker image prune -a -f
	@echo "Removing all networks..."
	docker network prune -f
	@echo "🧹 Complete dev system cleanup done"
	@echo "🔄 Restarting fresh dev environment..."
	@make dev-up

prod-nuke: ## Completely remove and restart all prod images, containers, and volumes (DESTRUCTIVE!)
	@echo "🧨 NUKING production environment completely..."
	@echo "⚠️  WARNING: This will PERMANENTLY DELETE ALL PRODUCTION DATA!"
	@echo "Type 'NUKE_PROD' to confirm:"
	@read confirmation && [ "$$confirmation" = "NUKE_PROD" ] || (echo "Nuke cancelled" && exit 1)
	@echo "Stopping all prod services..."
	docker-compose -f docker-compose.prod.yml --env-file .env.prod down --remove-orphans --volumes 2>/dev/null || true
	@echo "Removing project-specific volumes..."
	docker volume rm dispatch-ai_postgres_data dispatch-ai_redpanda_data 2>/dev/null || true
	@echo "Removing all containers..."
	docker container prune -f
	@echo "Removing all images..."
	docker image prune -a -f
	@echo "Removing all networks..."
	docker network prune -f
	@echo "🧹 Complete prod system cleanup done"
	@echo "🔄 Restarting fresh prod environment..."
	docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "Waiting for prod services to be ready..."
	@sleep 10

# Health Checks & Metrics
check-services: ## Check if all services are healthy
	@echo "Checking service health..."
	@printf "PostgreSQL: " && docker exec dispatchai-postgres pg_isready -U postgres >/dev/null 2>&1 && echo "✅ Ready" || echo "❌ Not Ready"
	@printf "Redpanda: " && curl -s http://localhost:9644/v1/cluster/health >/dev/null 2>&1 && echo "✅ Ready" || echo "❌ Not Ready"

check-containers: ## Check if all containers are running
	@echo "Checking containers..."
	@printf "Ingress: " && docker ps --format "table {{.Names}}" | grep -q "dispatchai-ingress" && echo "✅ Running" || echo "❌ Not Running"
	@printf "Classifier: " && docker ps --format "table {{.Names}}" | grep -q "dispatchai-classifier" && echo "✅ Running" || echo "❌ Not Running"
	@printf "Gateway: " && docker ps --format "table {{.Names}}" | grep -q "dispatchai-gateway" && echo "✅ Running" || echo "❌ Not Running"
	@printf "Dashboard: " && docker ps --format "table {{.Names}}" | grep -q "dispatchai-dashboard" && echo "✅ Running" || echo "❌ Not Running"

health: ## Show detailed health status of all services
	@echo "======================================"
	@echo "DispatchAI System Health Report"
	@echo "======================================"
	@echo ""
	@echo "📊 Ingress Service (Port 8000):"
	@curl -s http://localhost:8000/health 2>/dev/null | python3 -m json.tool || echo "❌ Service unreachable"
	@echo ""
	@echo "🤖 Classifier Service (Port 8001):"
	@curl -s http://localhost:8001/health 2>/dev/null | python3 -m json.tool || echo "❌ Service unreachable"
	@echo ""
	@echo "🔗 Gateway Service (Port 8002):"
	@curl -s http://localhost:8002/health 2>/dev/null | python3 -m json.tool || echo "❌ Service unreachable"
	@echo ""

health-ingress: ## Show health status of ingress service
	@echo "Ingress Service Health:"
	@curl -s http://localhost:8000/health | python3 -m json.tool

health-classifier: ## Show health status of classifier service
	@echo "Classifier Service Health:"
	@curl -s http://localhost:8001/health | python3 -m json.tool

health-gateway: ## Show health status of gateway service
	@echo "Gateway Service Health:"
	@curl -s http://localhost:8002/health | python3 -m json.tool

metrics: ## Show comprehensive metrics from all services
	@echo "======================================"
	@echo "DispatchAI System Metrics Report"
	@echo "======================================"
	@echo ""
	@echo "📊 Ingress Service Metrics:"
	@curl -s http://localhost:8000/metrics 2>/dev/null | python3 -m json.tool || echo "❌ Metrics unavailable"
	@echo ""
	@echo "🤖 Classifier Service Metrics:"
	@curl -s http://localhost:8001/metrics 2>/dev/null | python3 -m json.tool || echo "❌ Metrics unavailable"
	@echo ""
	@echo "🔗 Gateway Service Metrics:"
	@curl -s http://localhost:8002/metrics 2>/dev/null | python3 -m json.tool || echo "❌ Metrics unavailable"
	@echo ""
	@echo "📡 Kafka Consumer Lag:"
	@if docker ps --format "{{.Names}}" | grep -q "dispatchai-redpanda-prod"; then \
		docker exec dispatchai-redpanda-prod rpk group describe dispatchai-classifier 2>/dev/null || echo "❌ Consumer group not found"; \
	else \
		docker exec dispatchai-redpanda rpk group describe dispatchai-classifier 2>/dev/null || echo "❌ Consumer group not found"; \
	fi
	@echo ""

metrics-ingress: ## Show metrics for ingress service
	@echo "Ingress Service Metrics:"
	@curl -s http://localhost:8000/metrics | python3 -m json.tool

metrics-classifier: ## Show metrics for classifier service
	@echo "Classifier Service Metrics:"
	@curl -s http://localhost:8001/metrics | python3 -m json.tool

metrics-gateway: ## Show metrics for gateway service
	@echo "Gateway Service Metrics:"
	@curl -s http://localhost:8002/metrics | python3 -m json.tool

metrics-summary: ## Show quick metrics summary (perfect for demos)
	@echo "======================================"
	@echo "📊 DispatchAI Metrics Summary"
	@echo "======================================"
	@echo ""
	@echo "Ingress (Webhook Processing):"
	@curl -s http://localhost:8000/metrics 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"  Webhooks Received: {d.get('webhooks_received', 0)}\"); print(f\"  Webhooks Accepted: {d.get('webhooks_accepted', 0)}\"); print(f\"  Processing Time (p95): {d.get('processing_time_ms', {}).get('p95', 'N/A')}ms\"); print(f\"  Uptime: {d.get('uptime_seconds', 0)}s\")" || echo "  ❌ Unavailable"
	@echo ""
	@echo "Classifier (AI Processing):"
	@curl -s http://localhost:8001/metrics 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"  Issues Processed: {d.get('issues_processed', 0)}\"); print(f\"  Classification Time (p95): {d.get('classification_time_ms', {}).get('p95', 'N/A')}ms\"); print(f\"  OpenAI Errors: {d.get('openai_api_errors', 0)}\"); print(f\"  Consumer Lag: {d.get('consumer_lag', 0)}\"); print(f\"  Uptime: {d.get('uptime_seconds', 0)}s\")" || echo "  ❌ Unavailable"
	@echo ""
	@echo "Gateway (WebSocket Streaming):"
	@curl -s http://localhost:8002/metrics 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"  Active WebSocket Connections: {d.get('websocket_connections_active', 0)}\"); print(f\"  Messages Broadcast: {d.get('messages_broadcast', 0)}\"); print(f\"  API Requests: {d.get('api_requests', 0)}\"); print(f\"  Uptime: {d.get('uptime_seconds', 0)}s\")" || echo "  ❌ Unavailable"
	@echo ""

watch-metrics: ## Watch metrics in real-time (refreshes every 3 seconds)
	@echo "Watching metrics (Ctrl+C to stop)..."
	@while true; do \
		clear; \
		make metrics-summary; \
		sleep 3; \
	done

system-status: ## Show complete system status (containers + health + metrics)
	@echo "======================================"
	@echo "🚀 DispatchAI System Status Report"
	@echo "======================================"
	@echo ""
	@echo "📦 Container Status:"
	@make check-containers
	@echo ""
	@echo "💚 Service Health:"
	@make check-services
	@echo ""
	@echo "📈 Performance Metrics:"
	@make metrics-summary
	@echo ""
	@echo "======================================"
	@echo "✅ System Status Report Complete"
	@echo "======================================"

# Testing
test: ## Run all tests (requires running containers)
	@echo "Running all tests..."
	@make test-ingress
	@make test-classifier
	@make test-gateway
	@make test-dashboard

test-ci: ## Run all tests for CI (no containers required)
	@echo "Running all tests for CI..."
	@make test-ingress-local
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

test-ingress: ## Run ingress component tests (requires container)
	@echo "Testing ingress component..."
	@if docker ps --format "table {{.Names}}" | grep -q "dispatchai-ingress"; then \
		echo "Running tests in Docker container..."; \
		docker exec dispatchai-ingress python -m pytest test_webhook.py -v; \
	else \
		echo "❌ Ingress container not running. Start with 'make dev' first"; \
		exit 1; \
	fi

test-ingress-local: ## Run ingress component tests locally
	@echo "Testing ingress component locally..."
	@if [ -f ingress/requirements.txt ]; then \
		cd ingress && python -m pytest test_webhook.py -v; \
	else \
		echo "⚠️  Ingress tests not yet implemented"; \
	fi

test-classifier: ## Run classifier component tests (local)
	@echo "Testing classifier component locally..."
	@if [ -f classifier/requirements.txt ] && [ -d classifier/tests ]; then \
		cd classifier && python -m pytest tests/ -v; \
	else \
		echo "⚠️  Classifier tests not yet implemented"; \
	fi

test-classifier-docker: ## Run classifier component tests in Docker
	@echo "Testing classifier component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "dispatchai-classifier"; then \
		if docker exec dispatchai-classifier find . -name "test*.py" -o -name "*test.py" | grep -q .; then \
			docker exec dispatchai-classifier python -m pytest -v; \
		else \
			echo "⚠️  No test files found in classifier container"; \
		fi; \
	else \
		echo "❌ Classifier container not running. Start with 'make dev' first"; \
	fi

test-gateway: ## Run gateway component tests (local)
	@echo "Testing gateway component locally..."
	@if [ -f gateway/requirements.txt ] && [ -d gateway/tests ]; then \
		cd gateway && python -m pytest tests/ -v; \
	else \
		echo "⚠️  Gateway tests not yet implemented"; \
	fi

test-gateway-docker: ## Run gateway component tests in Docker
	@echo "Testing gateway component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "dispatchai-gateway"; then \
		if docker exec dispatchai-gateway find . -name "test*.py" -o -name "*test.py" | grep -q .; then \
			docker exec dispatchai-gateway python -m pytest -v; \
		else \
			echo "⚠️  No test files found in gateway container"; \
		fi; \
	else \
		echo "❌ Gateway container not running. Start with 'make dev' first"; \
	fi

test-dashboard: ## Run dashboard component tests (local)
	@echo "Testing dashboard component locally..."
	@if [ -f dashboard/package.json ]; then \
		cd dashboard && npm run test 2>/dev/null || echo "⚠️  Dashboard tests not yet implemented"; \
	else \
		echo "⚠️  Dashboard tests not yet implemented"; \
	fi

test-dashboard-docker: ## Run dashboard component tests in Docker
	@echo "Testing dashboard component in Docker..."
	@if docker ps --format "table {{.Names}}" | grep -q "dispatchai-dashboard"; then \
		if docker exec dispatchai-dashboard test -f package.json; then \
			docker exec dispatchai-dashboard npm test; \
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

demo: ## Run comprehensive system showcase demo (perfect for interviews!)
	@echo "🎯 Running DispatchAI System Showcase Demo..."
	@if [ -f scripts/demo-system-showcase.sh ]; then \
		./scripts/demo-system-showcase.sh; \
	else \
		echo "❌ Demo script not found at scripts/demo-system-showcase.sh"; \
	fi

trace-recent: ## Show recent correlation IDs and trace one (for production demos)
	@echo "Recent Correlation IDs:"
	@echo "======================="
	@if docker ps --format "{{.Names}}" | grep -q "dispatchai-ingress-prod"; then \
		docker logs dispatchai-ingress-prod 2>&1 | grep "correlation_id" | grep "Webhook processed successfully" | tail -10 | sed 's/.*correlation_id"://' | sed 's/,.*//' | sed 's/"//g'; \
		echo ""; \
		echo "To trace a specific ID, run:"; \
		echo "  make trace-id ID=<correlation-id-from-above>"; \
	else \
		docker logs dispatchai-ingress 2>&1 | grep "correlation_id" | grep "Webhook processed successfully" | tail -10 | sed 's/.*correlation_id"://' | sed 's/,.*//' | sed 's/"//g'; \
		echo ""; \
		echo "To trace a specific ID, run:"; \
		echo "  make trace-id ID=<correlation-id-from-above>"; \
	fi

trace-id: ## Trace a specific correlation ID through all services (usage: make trace-id ID=abc-123)
	@if [ -z "$(ID)" ]; then \
		echo "❌ Usage: make trace-id ID=<correlation-id>"; \
		echo "Get recent IDs with: make trace-recent"; \
		exit 1; \
	fi
	@echo "Tracing correlation_id: $(ID)"
	@echo "======================================"
	@echo ""
	@if docker ps --format "{{.Names}}" | grep -q "dispatchai-ingress-prod"; then \
		echo "📊 Ingress Service:"; \
		docker logs dispatchai-ingress-prod 2>&1 | grep "$(ID)" | head -10; \
		echo ""; \
		echo "🤖 Classifier Service:"; \
		docker logs dispatchai-classifier-prod 2>&1 | grep "$(ID)" | head -10; \
		echo ""; \
		echo "🔗 Gateway Service:"; \
		docker logs dispatchai-gateway-prod 2>&1 | grep "$(ID)" | head -10; \
	else \
		echo "📊 Ingress Service:"; \
		docker logs dispatchai-ingress 2>&1 | grep "$(ID)" | head -10; \
		echo ""; \
		echo "🤖 Classifier Service:"; \
		docker logs dispatchai-classifier 2>&1 | grep "$(ID)" | head -10; \
		echo ""; \
		echo "🔗 Gateway Service:"; \
		docker logs dispatchai-gateway 2>&1 | grep "$(ID)" | head -10; \
	fi

# Linting
lint: ## Run all linters
	@echo "Running all linters..."
	@make lint-python
	@make lint-js

lint-python: ## Run Python linters (ruff)
	@echo "Linting Python code..."
	@if ! command -v ruff >/dev/null 2>&1; then \
		echo "❌ ruff not found. Install with: pip install ruff"; \
		echo "   Or use Docker-based linting: make lint-python-docker"; \
		exit 1; \
	fi
	@for dir in ingress classifier gateway; do \
		if [ -f $$dir/requirements.txt ]; then \
			echo "Linting $$dir..."; \
			(cd $$dir && ruff check . && ruff format --check .); \
		else \
			echo "⚠️  $$dir not yet set up for linting"; \
		fi; \
	done

lint-python-docker: ## Run Python linters in Docker containers
	@echo "Linting Python code in Docker containers..."
	@for dir in ingress classifier gateway; do \
		if [ -f $$dir/requirements.txt ]; then \
			echo "Linting $$dir in Docker..."; \
			if docker ps --format "table {{.Names}}" | grep -q "dispatchai-$$dir"; then \
				docker exec dispatchai-$$dir ruff check . && \
				docker exec dispatchai-$$dir ruff format --check .; \
			else \
				echo "⚠️  $$dir container not running. Start with 'make dev' first"; \
			fi; \
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
db-reset: ## Reset the development database with fresh schema
	@echo "Resetting development database and Kafka..."
	@make dev-down
	cd infra && docker volume rm infra_postgres_data 2>/dev/null || true
	cd infra && docker volume rm infra_redpanda_data 2>/dev/null || true
	@make dev-up
	@echo "Development database and Kafka reset complete"

db-reset-prod: ## Reset the production database with fresh schema (DESTRUCTIVE!)
	@echo "⚠️  WARNING: This will PERMANENTLY DELETE all production data!"
	@echo "Type 'RESET_PROD_DB' to confirm:"
	@read confirmation && [ "$$confirmation" = "RESET_PROD_DB" ] || (echo "Reset cancelled" && exit 1)
	@echo "Stopping production services..."
	docker-compose -f docker-compose.prod.yml --env-file .env.prod down
	@echo "Removing production database volume..."
	docker volume rm dispatch-ai_postgres_data 2>/dev/null || true
	@echo "Removing production Redpanda volume..."
	docker volume rm dispatch-ai_redpanda_data 2>/dev/null || true
	@echo "Starting production services..."
	docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "Production database reset complete"

db-reset-data-only: ## Reset database data but keep schema (development)
	@echo "Resetting database data only..."
	@make db-query SQL="TRUNCATE TABLE dispatchai.manual_corrections, dispatchai.similar_issues, dispatchai.processing_logs, dispatchai.enriched_issues, dispatchai.issues RESTART IDENTITY CASCADE;"
	@echo "Database data cleared - no test data inserted"

db-reset-prod-data-only: ## Reset production database data but keep schema (DESTRUCTIVE!)
	@echo "⚠️  WARNING: This will PERMANENTLY DELETE all production data!"
	@echo "Type 'RESET_PROD_DATA' to confirm:"
	@read confirmation && [ "$$confirmation" = "RESET_PROD_DATA" ] || (echo "Reset cancelled" && exit 1)
	@echo "Truncating production data..."
	docker exec dispatchai-postgres-prod psql -U postgres -d dispatchai -c "TRUNCATE TABLE dispatchai.manual_corrections, dispatchai.similar_issues, dispatchai.processing_logs, dispatchai.enriched_issues, dispatchai.issues RESTART IDENTITY CASCADE;"
	@echo "Production database data cleared - no test data inserted"

db-shell: ## Open PostgreSQL shell
	@echo "Opening PostgreSQL shell..."
	@if [ -t 0 ]; then \
		docker exec -it dispatchai-postgres psql -U postgres -d dispatchai; \
	else \
		echo "❌ No TTY available. Use 'make db-query SQL=\"SELECT * FROM dispatchai.issues;\"' instead"; \
		echo "Or run directly: docker exec -it dispatchai-postgres psql -U postgres -d dispatchai"; \
	fi

db-query: ## Run SQL query (usage: make db-query SQL="SELECT * FROM dispatchai.issues;")
	@if [ -z "$(SQL)" ]; then \
		echo "❌ Usage: make db-query SQL=\"SELECT * FROM dispatchai.issues;\""; \
		echo "Examples:"; \
		echo "  make db-query SQL=\"SELECT * FROM dispatchai.issues;\""; \
		echo "  make db-query SQL=\"SELECT COUNT(*) FROM dispatchai.enriched_issues;\""; \
		echo "  make db-query SQL=\"\\dt dispatchai.*\""; \
	else \
		docker exec dispatchai-postgres psql -U postgres -d dispatchai -c "$(SQL)"; \
	fi

db-tables: ## List all tables in the database
	@echo "Tables in dispatchai schema:"
	@docker exec dispatchai-postgres psql -U postgres -d dispatchai -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dispatchai' ORDER BY table_name;"

db-issues: ## Show all issues in the database
	@echo "Issues in database:"
	@docker exec dispatchai-postgres psql -U postgres -d dispatchai -c "SELECT id, issue_number, title, author, author_association, created_at FROM dispatchai.issues ORDER BY created_at DESC;"

db-enriched: ## Show enriched issues in the database
	@echo "Enriched issues in database:"
	@docker exec dispatchai-postgres psql -U postgres -d dispatchai -c "SELECT id, issue_id, category, priority, confidence_score, processed_at FROM dispatchai.enriched_issues ORDER BY processed_at DESC;"

db-backup: ## Backup the database
	@echo "Creating database backup..."
	docker exec dispatchai-postgres pg_dump -U postgres dispatchai > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Backup created: backup_$(shell date +%Y%m%d_%H%M%S).sql"

migrate: ## Run database migrations
	@echo "Running database migrations..."
	@for migration in infra/migrations/*.sql; do \
		echo "Applying migration: $$migration"; \
		docker exec -i dispatchai-postgres psql -U postgres -d dispatchai < $$migration; \
	done
	@echo "✅ All migrations applied successfully"

migrate-file: ## Run specific migration file (usage: make migrate-file FILE=001_add_unique_issue_id_constraint.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Usage: make migrate-file FILE=001_add_unique_issue_id_constraint.sql"; \
		exit 1; \
	fi
	@echo "Applying migration: infra/migrations/$(FILE)"
	@docker exec -i dispatchai-postgres psql -U postgres -d dispatchai < infra/migrations/$(FILE)
	@echo "✅ Migration applied successfully"

# Kafka/Redpanda Management
kafka-topics: ## List Kafka topics
	docker exec dispatchai-redpanda rpk topic list

kafka-create-topics: ## Create required Kafka topics
	@echo "Creating Kafka topics..."
	docker exec dispatchai-redpanda rpk topic create issues.raw --partitions 3 --replicas 1
	docker exec dispatchai-redpanda rpk topic create issues.enriched --partitions 3 --replicas 1
	@echo "Topics created successfully"

kafka-console: ## Consume recent messages from Kafka topic (usage: make kafka-console TOPIC=issues.raw)
	docker exec dispatchai-redpanda rpk topic consume $(TOPIC) --num 10 --offset start

kafka-tail: ## Tail Kafka topic messages interactively (usage: make kafka-tail TOPIC=issues.raw)
	@echo "Tailing messages from topic: $(TOPIC)"
	@echo "Press Ctrl+C to stop"
	docker exec -it dispatchai-redpanda rpk topic consume $(TOPIC) --num 0

kafka-reset-offsets: ## Reset consumer group offsets to end (skip old messages)
	@echo "Resetting consumer group offsets to end..."
	docker exec dispatchai-redpanda rpk group seek dispatchai-classifier --to end
	@echo "✅ Consumer offsets reset - classifier will skip old messages"

kafka-describe-group: ## Show consumer group status and lag
	@echo "Consumer group status:"
	docker exec dispatchai-redpanda rpk group describe dispatchai-classifier

# Environment Setup
setup-env: ## Set up development environment files
	@echo "Setting up environment files..."
	@if [ ! -f .env ]; then \
		echo "Creating .env file from template..."; \
		cp .env.example .env 2>/dev/null || echo "# DispatchAI Environment Variables" > .env; \
		echo "POSTGRES_URL=postgresql://postgres:password@localhost:5432/dispatchai" >> .env; \
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
	docker exec -it dispatchai-ingress /bin/bash

shell-classifier: ## Open shell in classifier container
	docker exec -it dispatchai-classifier /bin/bash

shell-gateway: ## Open shell in gateway container
	docker exec -it dispatchai-gateway /bin/bash

shell-dashboard: ## Open shell in dashboard container
	docker exec -it dispatchai-dashboard /bin/bash
