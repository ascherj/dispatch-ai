#!/bin/bash

# Detect script location and ensure we can find other scripts
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Testing Correlation ID Tracing ==="
echo ""
echo "Sending webhook..."
RESPONSE=$($SCRIPT_DIR/send_webhook.sh 2>&1)
echo "$RESPONSE"
echo ""

# Extract correlation ID from response
CORR_ID=$(echo "$RESPONSE" | grep -o '"correlation_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$CORR_ID" ]; then
    echo "❌ Failed to extract correlation ID from response"
    exit 1
fi

echo "✅ Generated Correlation ID: $CORR_ID"
echo ""
echo "Waiting 3 seconds for message processing..."
sleep 3
echo ""

echo "=== Tracing through services ==="
echo ""

echo "1️⃣  INGRESS SERVICE:"
docker logs dispatchai-ingress 2>&1 | grep "$CORR_ID" | tail -3
echo ""

echo "2️⃣  CLASSIFIER SERVICE:"
docker logs dispatchai-classifier 2>&1 | grep "$CORR_ID" | tail -3
echo ""

echo "3️⃣  GATEWAY SERVICE:"
docker logs dispatchai-gateway 2>&1 | grep "$CORR_ID" | tail -3
echo ""

echo "✅ End-to-end tracing complete!"
echo ""
echo "You can trace any webhook using:"
echo "  docker logs dispatchai-ingress 2>&1 | grep <correlation-id>"
echo "  docker logs dispatchai-classifier 2>&1 | grep <correlation-id>"
echo "  docker logs dispatchai-gateway 2>&1 | grep <correlation-id>"
