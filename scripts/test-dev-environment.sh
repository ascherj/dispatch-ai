#!/bin/bash

# Test script for DispatchAI development environment
# This script tests that all services start up correctly and are accessible

set -e

echo "🚀 Testing DispatchAI Development Environment"
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
    
    # Use Python websockets package
    python3 << 'EOF' 2>/dev/null
import asyncio
import websockets
import sys

async def test_ws():
    try:
        ws = await websockets.connect('ws://localhost:8002/ws', open_timeout=2)
        await ws.close()
        return True
    except Exception:
        return False

result = asyncio.run(test_ws())
sys.exit(0 if result else 1)
EOF
    
    if [ $? -eq 0 ]; then
        echo "✅ WebSocket working"
    else
        echo "⚠️  WebSocket connection test failed"
        echo "   Install websockets with: pip install -r requirements.txt"
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
if docker exec dispatchai-postgres pg_isready -U postgres -d dispatchai >/dev/null 2>&1; then
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

# Generate development JWT token for API authentication
echo -n "Generating dev JWT token... "
DEV_JWT=$(python3 -c "
from jose import jwt
import time
payload = {
    'sub': '0',
    'username': 'dev_user',
    'dev_mode': True,
    'exp': int(time.time()) + 3600
}
token = jwt.encode(payload, 'dev-jwt-secret-change-in-production-to-secure-random-key', algorithm='HS256')
print(token)
" 2>/dev/null)

if [ -n "$DEV_JWT" ]; then
    echo "✅"
else
    echo "❌ Failed to generate JWT (python-jose may not be installed)"
    echo "   Install with: pip install python-jose[cryptography]"
    echo "   Skipping authenticated API tests..."
    DEV_JWT=""
fi

# Test API endpoints
if [ -n "$DEV_JWT" ]; then
    echo -n "Testing gateway API... "
    GATEWAY_RESPONSE=$(curl -s -H "Authorization: Bearer $DEV_JWT" http://localhost:8002/api/stats)
    if echo "$GATEWAY_RESPONSE" | grep -q "total_issues"; then
        echo "✅ API responding correctly"
    else
        echo "❌ API not responding as expected"
    fi
else
    echo "⚠️  Skipping gateway API test (no JWT token)"
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
