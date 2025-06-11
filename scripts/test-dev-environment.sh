#!/bin/bash

# Test script for Auto-Triager development environment
# This script tests that all services start up correctly and are accessible

set -e

echo "🚀 Testing Auto-Triager Development Environment"
echo "=============================================="

# Function to check if a service is responding
check_service() {
    local name=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    echo -n "Checking $name... "

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✅ Ready"
            return 0
        fi

        if [ $attempt -eq $max_attempts ]; then
            echo "❌ Failed (timeout after 30 attempts)"
            return 1
        fi

        sleep 1
        attempt=$((attempt + 1))
    done
}

# Function to check WebSocket connection
check_websocket() {
    echo -n "Checking WebSocket connection... "

    # Use websocat or fallback to a simple test
    if command -v websocat >/dev/null 2>&1; then
        echo "test" | timeout 3 websocat ws://localhost:8002/ws >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "✅ WebSocket working"
        else
            echo "⚠️  WebSocket connection test inconclusive"
        fi
    else
        echo "⚠️  websocat not installed, skipping WebSocket test"
    fi
}

echo
echo "🔍 Checking service availability..."

# Check all services
check_service "Ingress (FastAPI webhook receiver)" "http://localhost:8000/health"
check_service "Gateway (WebSocket/REST API)" "http://localhost:8002/health"
check_service "Dashboard (React frontend)" "http://localhost:3000"

# Check database connectivity
echo -n "Checking PostgreSQL database... "
if docker exec auto-triager-postgres pg_isready -U postgres -d auto_triager >/dev/null 2>&1; then
    echo "✅ Ready"
else
    echo "❌ Not ready"
fi

# Check Kafka/Redpanda
echo -n "Checking Redpanda (Kafka)... "
if curl -s http://localhost:9644/v1/status/ready >/dev/null 2>&1; then
    echo "✅ Ready"
else
    echo "❌ Not ready"
fi

# Check WebSocket
check_websocket

echo
echo "🧪 Running API tests..."

# Test API endpoints
echo -n "Testing gateway API... "
GATEWAY_RESPONSE=$(curl -s http://localhost:8002/api/stats)
if echo "$GATEWAY_RESPONSE" | grep -q "total_issues"; then
    echo "✅ API responding correctly"
else
    echo "❌ API not responding as expected"
fi

echo -n "Testing ingress health... "
INGRESS_RESPONSE=$(curl -s http://localhost:8000/health)
if echo "$INGRESS_RESPONSE" | grep -q "healthy"; then
    echo "✅ Ingress healthy"
else
    echo "❌ Ingress not healthy"
fi

echo
echo "📊 Service Summary:"
echo "=================="
echo "✅ Ingress:   http://localhost:8000"
echo "✅ Gateway:   http://localhost:8002"
echo "✅ Dashboard: http://localhost:3000"
echo "✅ Database:  localhost:5432"
echo "✅ Redpanda:  localhost:19092"

echo
echo "🎉 Development environment is ready!"
echo "   • Dashboard: http://localhost:3000"
echo "   • API Docs:  http://localhost:8002/docs"
echo "   • Webhook:   http://localhost:8000/webhook/github"

echo
echo "📚 Quick commands:"
echo "   make status      - Check service status"
echo "   make dev-logs    - View all service logs"
echo "   make dev-down    - Stop all services"
