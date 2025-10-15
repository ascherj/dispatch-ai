#!/bin/bash
set -e

echo "======================================"
echo "🎯 DispatchAI System Showcase Demo"
echo "======================================"
echo ""
echo "This script demonstrates the complete observability"
echo "and monitoring capabilities of the DispatchAI system."
echo ""

echo "Step 1: Verify all services are running..."
echo "==========================================="
make check-containers
echo ""
sleep 2

echo "Step 2: Check service health (with dependency verification)..."
echo "=============================================================="
echo ""
echo "This shows that health checks verify dependencies, not just 200 OK responses."
echo ""
make health-ingress
echo ""
sleep 2

echo "Step 3: View current system metrics..."
echo "======================================="
echo ""
echo "These metrics show p50/p95/p99 latencies, consumer lag, and operational stats."
echo ""
make metrics-summary
echo ""
sleep 3

echo "Step 4: Send a test webhook to demonstrate E2E processing..."
echo "============================================================"
echo ""

WEBHOOK_PAYLOAD=$(cat <<'EOF'
{
  "action": "opened",
  "issue": {
    "id": 999999,
    "number": 123,
    "title": "Demo: Application crashes on startup",
    "body": "When I try to start the app, it immediately crashes with a segmentation fault. This is a critical bug that needs immediate attention. Steps to reproduce: 1. Run the app 2. App crashes immediately 3. See segfault error in logs",
    "user": {
      "id": 12345,
      "login": "demo-user",
      "avatar_url": "https://github.com/demo-user.png",
      "html_url": "https://github.com/demo-user"
    },
    "state": "open",
    "html_url": "https://github.com/demo-user/demo-repo/issues/123",
    "created_at": "2025-10-15T12:00:00Z",
    "updated_at": "2025-10-15T12:00:00Z"
  },
  "repository": {
    "id": 1,
    "name": "demo-repo",
    "full_name": "demo-user/demo-repo",
    "html_url": "https://github.com/demo-user/demo-repo",
    "private": false,
    "owner": {
      "id": 12345,
      "login": "demo-user",
      "avatar_url": "https://github.com/demo-user.png",
      "html_url": "https://github.com/demo-user"
    }
  },
  "sender": {
    "id": 12345,
    "login": "demo-user",
    "avatar_url": "https://github.com/demo-user.png",
    "html_url": "https://github.com/demo-user"
  }
}
EOF
)

echo "Sending webhook to http://localhost:8000/webhook/github..."
RESPONSE=$(curl -s -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d "$WEBHOOK_PAYLOAD")

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
CORRELATION_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('correlation_id', 'N/A'))" 2>/dev/null || echo "N/A")
echo ""
echo "✅ Webhook sent with correlation_id: $CORRELATION_ID"
echo ""
sleep 2

echo "Step 5: Wait for processing to complete..."
echo "==========================================="
echo "Processing typically takes 3-5 seconds (mostly OpenAI API latency)..."
echo ""
for i in {1..5}; do
    echo "⏳ Waiting... ${i}s"
    sleep 1
done
echo ""

echo "Step 6: View updated metrics (after processing)..."
echo "=================================================="
echo ""
make metrics-summary
echo ""
sleep 2

echo "Step 7: Trace the issue through all services using correlation ID..."
echo "===================================================================="
echo ""
echo "This demonstrates E2E distributed tracing capability."
echo "Searching logs for correlation_id: $CORRELATION_ID"
echo ""

if [ "$CORRELATION_ID" != "N/A" ]; then
    echo "--- Ingress Service Logs ---"
    docker logs dispatchai-ingress 2>&1 | grep "$CORRELATION_ID" | tail -5 || echo "No logs found"
    echo ""
    
    echo "--- Classifier Service Logs ---"
    docker logs dispatchai-classifier 2>&1 | grep "$CORRELATION_ID" | tail -5 || echo "Processing may still be in progress or logs not yet available"
    echo ""
    
    echo "--- Gateway Service Logs ---"
    docker logs dispatchai-gateway 2>&1 | grep "$CORRELATION_ID" | tail -5 || echo "Processing may still be in progress or logs not yet available"
    echo ""
else
    echo "⚠️  Could not extract correlation ID from response"
fi

sleep 2

echo "======================================"
echo "✅ Demo Complete!"
echo "======================================"
echo ""
echo "Key Takeaways:"
echo "-------------"
echo "1. ✅ All services expose /health endpoints with dependency verification"
echo "2. ✅ All services expose /metrics endpoints with p50/p95/p99 latencies"
echo "3. ✅ Correlation IDs enable E2E tracing in <1 minute"
echo "4. ✅ System processes webhooks in 3-5 seconds end-to-end"
echo "5. ✅ Consumer lag monitoring shows classifier keeping up with load"
echo ""
echo "Available Commands:"
echo "------------------"
echo "  make health              - View all service health checks"
echo "  make metrics             - View comprehensive metrics"
echo "  make metrics-summary     - View quick metrics summary"
echo "  make system-status       - View complete system status"
echo "  make watch-metrics       - Watch metrics in real-time"
echo ""
echo "For detailed analysis:"
echo "  make health-ingress      - Ingress service health only"
echo "  make metrics-classifier  - Classifier service metrics only"
echo "  make kafka-describe-group - View Kafka consumer lag details"
echo ""
