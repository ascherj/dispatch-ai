#!/bin/bash
set -e

echo "🚀 Starting DispatchAI Production Environment"

# Check if .env.prod exists
if [ ! -f .env.prod ]; then
    echo "❌ .env.prod file not found!"
    echo "   Copy .env.prod.example to .env.prod and configure your values"
    exit 1
fi

# Check required environment variables
source .env.prod

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY is required in .env.prod"
    exit 1
fi

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "❌ POSTGRES_PASSWORD is required in .env.prod"
    exit 1
fi

echo "✅ Environment variables validated"

# Build and start services
echo "🔨 Building production images..."
docker compose -f docker-compose.prod.yml --env-file .env.prod build

echo "🚀 Starting production services..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
echo "🔍 Checking service health..."
SERVICES=("postgres" "redpanda" "ingress" "classifier" "gateway" "dashboard")

for service in "${SERVICES[@]}"; do
    if docker compose -f docker-compose.prod.yml ps --format json | jq -r ".[].Service" | grep -q "$service"; then
        echo "✅ $service is running"
    else
        echo "❌ $service failed to start"
    fi
done

echo ""
echo "🎉 DispatchAI Production Environment Started!"
echo ""
echo "📊 Dashboard:     http://localhost:3000"
echo "🌐 Gateway API:   http://localhost:8002"
echo "📥 Webhook URL:   http://localhost:8000/webhook/github"
echo "🔍 Kafka Console: http://localhost:8080 (run with --profile tools)"
echo ""
echo "📝 View logs: docker compose -f docker-compose.prod.yml logs -f"
echo "🛑 Stop:      docker compose -f docker-compose.prod.yml down"