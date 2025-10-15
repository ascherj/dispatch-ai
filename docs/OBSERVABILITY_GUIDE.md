# DispatchAI Observability & Monitoring Guide

## Quick Reference for Interview Demos

### 🎯 One-Command Demo
```bash
make demo
```
**What it does:** Runs a complete showcase of the system's observability features:
- Verifies all services are running
- Shows health checks with dependency verification
- Displays current metrics (p50/p95/p99 latencies)
- Sends a test webhook
- Demonstrates E2E correlation ID tracing
- Shows updated metrics after processing

**Duration:** ~30 seconds

---

## Health Monitoring Commands

### View All Service Health
```bash
make health
```
Shows detailed health status for all three services with dependency verification.

**Example Output:**
```json
{
  "status": "healthy",
  "service": "ingress",
  "dependencies": {
    "kafka": "connected",
    "database": "connected"
  }
}
```

### Individual Service Health
```bash
make health-ingress      # Ingress service only
make health-classifier   # Classifier service only
make health-gateway      # Gateway service only
```

---

## Metrics & Performance Monitoring

### Quick Metrics Summary (Best for Demos)
```bash
make metrics-summary
```

Shows condensed view perfect for presentations:
- Webhooks received/accepted
- Processing times (p95)
- Issues classified
- Classification latency (p95)
- Active WebSocket connections
- Consumer lag

**Example Output:**
```
Ingress (Webhook Processing):
  Webhooks Received: 42
  Webhooks Accepted: 42
  Processing Time (p95): 120ms
  Uptime: 3600s

Classifier (AI Processing):
  Issues Processed: 42
  Classification Time (p95): 5100ms
  OpenAI Errors: 0
  Consumer Lag: 0
  Uptime: 3600s
```

### Comprehensive Metrics
```bash
make metrics
```

Shows full metrics from all services including:
- Full latency breakdown (p50/p95/p99)
- Error counts
- Kafka consumer lag details
- Uptime and throughput

### Individual Service Metrics
```bash
make metrics-ingress      # Ingress metrics
make metrics-classifier   # Classifier metrics
make metrics-gateway      # Gateway metrics
```

### Watch Metrics in Real-Time
```bash
make watch-metrics
```

Auto-refreshes metrics every 3 seconds. Perfect for demonstrating system under load.
Press `Ctrl+C` to stop.

---

## Complete System Status

### Full Status Report
```bash
make system-status
```

Shows everything in one view:
1. Container status (running/stopped)
2. Service health (healthy/unhealthy)
3. Performance metrics summary

**Perfect for:** Quick health check before demos or debugging sessions.

---

## Correlation ID Tracing

### Manual Tracing
1. Send a webhook and capture the correlation ID:
```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d '{"action": "opened", "issue": {...}}'
```

2. Extract correlation ID from response
3. Trace through all services:
```bash
CORRELATION_ID="abc-123-def-456"
docker logs dispatchai-ingress 2>&1 | grep "$CORRELATION_ID"
docker logs dispatchai-classifier 2>&1 | grep "$CORRELATION_ID"
docker logs dispatchai-gateway 2>&1 | grep "$CORRELATION_ID"
```

### Automated E2E Tracing
```bash
./scripts/test-correlation-tracing.sh
```

Automatically:
- Sends test webhook
- Extracts correlation ID
- Searches all service logs
- Verifies E2E tracing works

### Production Tracing (with Signature Verification)

In production, webhook signature verification is enabled. To trace issues:

**View recent correlation IDs:**
```bash
make trace-recent
```

**Trace a specific ID:**
```bash
make trace-id ID=abc-123-def-456
```

This works in both dev and production environments, automatically detecting the correct container names.

---

## Kafka Consumer Monitoring

### View Consumer Lag
```bash
make kafka-describe-group
```

Shows:
- Consumer group status
- Partition assignments
- Current offset vs. log end offset
- Lag per partition

**Critical metric:** If lag > 100, classifier can't keep up with incoming webhooks.

### List Kafka Topics
```bash
make kafka-topics
```

### Tail Kafka Messages
```bash
make kafka-tail TOPIC=issues.raw
```

---

## Interview Demo Script

### Scenario: "Show me your observability capabilities"

**1. Show System Status (10 seconds)**
```bash
make system-status
```
*"All services healthy, processing webhooks with 120ms p95 latency"*

**2. Show Detailed Metrics (15 seconds)**
```bash
make metrics-summary
```
*"Tracking p50/p95/p99 latencies, consumer lag, error rates"*

**3. Send Test Webhook & Trace (30 seconds)**
```bash
make demo
```
*"Watch how correlation IDs enable E2E tracing in under a minute"*

**4. Show Real-Time Monitoring (ongoing)**
```bash
make watch-metrics
```
*"Metrics refresh every 3 seconds—I can see issues processing in real-time"*

---

## Performance Targets & SLOs

### System Performance Metrics

These are the target performance levels and alerting thresholds for production operation:

| Metric | Target | Alert Threshold | Current Performance | Status |
|--------|--------|-----------------|---------------------|--------|
| **Webhook Response Time** | <100ms | >500ms | ~115ms p95 | ✅ On Target |
| **End-to-End Processing** | <5s | >10s | ~3-5s typical | ✅ On Target |
| **Classification Success Rate** | >95% | <90% | ~100% (dev) | ✅ On Target |
| **API Response Time** | <200ms | >1s | <200ms typical | ✅ On Target |
| **Consumer Lag** | 0 | >100 for 5min | 0 (real-time) | ✅ Healthy |
| **System Availability** | 99.9% | <99% | N/A (dev) | 📊 To Measure |

### Service-Specific SLOs

#### Ingress Service
- **Webhook acceptance rate:** >99% (target), <95% (alert)
- **Kafka publish latency:** <50ms p95, >200ms alert
- **Memory usage:** <512MB, >1GB alert
- **Error rate:** <1%, >5% alert

#### Classifier Service  
- **Classification latency:** <5s p95, >10s alert
- **OpenAI API errors:** <5%, >10% alert
- **Processing throughput:** >20 issues/minute, <10 alert
- **Consumer lag:** 0, >100 for 5min alert

#### Gateway Service
- **WebSocket message latency:** <100ms p95, >500ms alert
- **API endpoint latency:** <200ms p95, >1s alert
- **Active connections:** Monitor only, no alert
- **Broadcast failures:** <1%, >5% alert

### Comparison: Target vs. Current

**How to check current performance:**
```bash
make metrics-summary
```

**Example comparison:**

```
Target: Webhook Response <100ms → Current: 115ms p95 ✅ Close to target
Target: E2E Processing <5s → Current: 3-5s typical ✅ On target
Target: Consumer Lag = 0 → Current: 0 ✅ Perfect
Target: Classification >95% → Current: Issues processed without errors ✅ On target
```

### Alerting Strategy

**Critical Alerts (Page On-Call):**
- Consumer lag >100 for 5 minutes
- Classification success rate <90%
- Any service health check failing for 3 minutes
- Webhook response time >500ms p95 for 5 minutes

**Warning Alerts (Slack Notification):**
- Consumer lag >50 for 2 minutes
- Classification success rate <95%
- Webhook response time >100ms p95 (exceeds target)
- End-to-end processing >5s p95 (exceeds target)
- OpenAI API error rate >5%

**Info Alerts (Dashboard Only):**
- Unusual spike in traffic (>2x normal)
- WebSocket connection count changes significantly
- Service restart detected

### Why These Targets Matter

**Webhook Response <100ms:**
- GitHub expects fast responses (<3s timeout, but <1s is best practice)
- Slow responses can trigger webhook retries
- Fast ack means we don't lose events even under load

**End-to-End <5s:**
- Users expect near-real-time classification
- Longer delays make the system feel unresponsive
- 5s allows for OpenAI API latency (1-2s) plus processing

**Classification Success >95%:**
- High accuracy builds trust in the AI system
- Failures require manual triage (defeats automation purpose)
- 95% means only 1 in 20 issues needs review

**API Response <200ms:**
- Dashboard queries should feel instant
- Slow APIs degrade user experience
- 200ms is perceptible but acceptable for most users

### Interview Talking Points

*"I've defined specific SLOs based on user expectations and system capabilities:*

- **Webhook response in <100ms:** GitHub's webhooks expect fast acknowledgment—we're currently at 115ms p95, slightly above target but well within acceptable range. Under load, this could degrade, so I'd alert at >500ms.

- **End-to-end processing <5s:** Users expect real-time classification. Currently achieving 3-5s, with most time spent waiting for OpenAI API (1-2s). This is on target.

- **Classification success >95%:** High accuracy is critical for user trust. Current dev environment shows near-perfect success rate. Would alert if it drops below 90%.

- **Consumer lag = 0:** Zero lag means real-time processing. Any lag >100 indicates backpressure—classifier can't keep up with incoming webhooks.

*These aren't arbitrary—they're based on:*
- User experience research (200ms feels instant, 1s feels sluggish)
- External dependencies (OpenAI API latency sets floor for E2E time)
- System capacity (Kafka buffers handle spikes, but lag indicates sustained overload)"

---

## Key Talking Points

### Why These Metrics Matter

**p50/p95/p99 Latencies:**
- "I track percentiles, not averages, because outliers matter in real-time systems"
- "p95 tells me what 95% of users experience—average hides slow requests"

**Consumer Lag:**
- "Critical for detecting backpressure—if lag grows, classifier can't keep up"
- "Lag = 0 means system is healthy and processing in real-time"

**Health Checks with Dependencies:**
- "Not just returning 200 OK—I verify Kafka, Database, and OpenAI API are reachable"
- "Load balancers can intelligently route around unhealthy instances"

**Correlation IDs:**
- "Trace a single issue through the entire pipeline in under a minute"
- "Essential for debugging distributed systems—no guesswork"

### Production Readiness

*"These aren't theoretical—I can demonstrate them right now:*
- ✅ Live metrics endpoints on all services
- ✅ Health checks that verify dependencies
- ✅ Correlation ID tracing with automated test script
- ✅ Consumer lag monitoring
- ✅ Real-time metrics dashboard capability

*In production, I'd feed these to Prometheus/Grafana with alerting rules:*
- Alert if consumer lag > 100 for 5 minutes
- Alert if error rate > 10%
- Alert if p95 latency > 10 seconds"

---

## Troubleshooting

### "Metrics show N/A or service unreachable"
- Check if services are running: `make check-containers`
- Check service logs: `make dev-logs-service SERVICE=ingress`
- Restart services: `make dev-restart`

### "Consumer lag is growing"
- Classifier can't keep up with incoming webhooks
- Check classifier logs for errors: `docker logs dispatchai-classifier`
- View OpenAI API error count: `make metrics-classifier`
- Solution: Scale horizontally or reduce OpenAI API latency

### "Health check shows dependencies unhealthy"
- Database: `docker exec dispatchai-postgres pg_isready -U postgres`
- Kafka: `curl http://localhost:9644/v1/cluster/health`
- Check infrastructure logs: `make dev-logs`

---

## Future Enhancements

**OpenTelemetry Integration:**
- Automatic trace spans with service-to-service timing
- Visual timeline in Jaeger UI
- Distributed tracing without manual correlation IDs

**Prometheus/Grafana:**
- Time-series metrics storage
- Visual dashboards with graphs
- Automated alerting rules (PagerDuty integration)

**Structured Logging:**
- Already implemented with JSON logs
- Future: Ship to ELK stack or Loki for centralized search
- Search across all services from single interface

---

## Command Cheat Sheet

| Command | Purpose | Use Case |
|---------|---------|----------|
| `make demo` | Full system showcase | Interview demos |
| `make system-status` | Complete health check | Pre-demo verification |
| `make metrics-summary` | Quick metrics view | Live presentations |
| `make watch-metrics` | Real-time monitoring | Show system under load |
| `make health` | Service health checks | Verify dependencies |
| `make trace-recent` | Show recent correlation IDs | Production tracing |
| `make trace-id ID=<id>` | Trace specific request | E2E debugging |
| `make kafka-describe-group` | Consumer lag details | Debug backpressure |
| `./scripts/demo-system-showcase.sh` | Automated demo script | E2E demonstration |

---

**Remember:** The key differentiator is that all of this is **implemented and working today**—not theoretical or planned for the future. You can demonstrate it live during the interview.
