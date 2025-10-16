# DispatchAI Observability Improvements Plan

## Executive Summary

This document outlines a phased approach to enhance observability beyond the current custom in-memory metrics solution. The plan introduces industry-standard tooling (Prometheus, Grafana, OpenTelemetry) while maintaining the working correlation ID tracing and health check infrastructure.

## Current State Assessment

### ✅ What's Working
- Custom `ServiceMetrics` class tracking counters and latencies
- Health endpoints with dependency verification (Kafka, PostgreSQL, OpenAI)
- Correlation ID tracing through structured logs
- JSON-formatted logging with structlog
- `/health` and `/metrics` endpoints on all services
- Make commands for metrics inspection

### ❌ Current Limitations
- **No persistence:** Metrics lost on service restart
- **No visualization:** Manual curl + jq for metrics
- **No alerting:** SLOs defined but not monitored
- **Manual tracing:** grep-based correlation ID tracking
- **Limited aggregation:** Can't compare metrics across time periods
- **No historical analysis:** Can't identify trends or regressions

## Recommended Improvements

### Phase 1: Prometheus + Grafana (Priority: HIGH)
**Timeline:** 1-2 days  
**Effort:** Low-Medium  
**Impact:** High

#### Implementation Steps

1. **Add Prometheus + Grafana to docker-compose.yml**
   ```yaml
   prometheus:
     image: prom/prometheus:v2.48.0
     container_name: dispatchai-prometheus
     ports:
       - "9090:9090"
     volumes:
       - ./prometheus.yml:/etc/prometheus/prometheus.yml
       - prometheus_data:/prometheus
     command:
       - '--config.file=/etc/prometheus/prometheus.yml'
       - '--storage.tsdb.retention.time=30d'
     networks:
       - dispatchai-network
   
   grafana:
     image: grafana/grafana:10.2.2
     container_name: dispatchai-grafana
     ports:
       - "3001:3000"
     environment:
       - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
       - GF_USERS_ALLOW_SIGN_UP=false
     volumes:
       - grafana_data:/var/lib/grafana
       - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
       - ./grafana/datasources:/etc/grafana/provisioning/datasources
     depends_on:
       - prometheus
     networks:
       - dispatchai-network
   ```

2. **Create prometheus.yml configuration**
   ```yaml
   global:
     scrape_interval: 15s
     evaluation_interval: 15s
   
   scrape_configs:
     - job_name: 'ingress'
       static_configs:
         - targets: ['ingress:8000']
     
     - job_name: 'classifier'
       static_configs:
         - targets: ['classifier:8001']
     
     - job_name: 'gateway'
       static_configs:
         - targets: ['gateway:8002']
     
     - job_name: 'auth'
       static_configs:
         - targets: ['auth:8003']
   ```

3. **Add prometheus_client to requirements**
   ```txt
   prometheus-client==0.19.0
   prometheus-fastapi-instrumentator==6.1.0
   ```

4. **Replace ServiceMetrics classes**
   
   **Files to modify:**
   - `gateway/app.py:99-150`
   - `classifier/app.py:59-109`
   - `ingress/app.py` (add metrics tracking)
   
   **Example replacement (gateway/app.py):**
   ```python
   from prometheus_client import Counter, Histogram, Gauge, generate_latest
   from prometheus_fastapi_instrumentator import Instrumentator
   
   # Metrics definitions
   websocket_connections = Gauge(
       'websocket_connections_active',
       'Number of active WebSocket connections'
   )
   
   messages_broadcast = Counter(
       'messages_broadcast_total',
       'Total messages broadcast to WebSocket clients'
   )
   
   api_requests = Counter(
       'api_requests_total',
       'Total API requests',
       ['endpoint', 'method', 'status']
   )
   
   api_latency = Histogram(
       'api_request_duration_seconds',
       'API request latency in seconds',
       ['endpoint', 'method'],
       buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
   )
   
   # Auto-instrument FastAPI
   Instrumentator().instrument(app).expose(app, endpoint="/metrics")
   ```

5. **Create Grafana dashboards**
   - Service overview dashboard (all services)
   - Per-service detailed dashboard
   - SLO compliance dashboard
   - Kafka consumer lag dashboard

#### Benefits
- ✅ Persistent metrics storage (30-day retention)
- ✅ Visual dashboards for all metrics
- ✅ Historical trend analysis
- ✅ Industry-standard format for future integrations
- ✅ Foundation for alerting (Phase 3)

#### Migration Path
Keep existing `/metrics` endpoints temporarily for backward compatibility. Remove after Phase 1 validation.

---

### Phase 2: OpenTelemetry + Distributed Tracing (Priority: MEDIUM)
**Timeline:** 2-3 days  
**Effort:** Medium  
**Impact:** High

#### Implementation Steps

1. **Add OpenTelemetry dependencies**
   ```txt
   opentelemetry-api==1.21.0
   opentelemetry-sdk==1.21.0
   opentelemetry-instrumentation-fastapi==0.42b0
   opentelemetry-instrumentation-kafka-python==0.42b0
   opentelemetry-instrumentation-psycopg2==0.42b0
   opentelemetry-exporter-jaeger==1.21.0
   ```

2. **Add Jaeger to docker-compose.yml**
   ```yaml
   jaeger:
     image: jaegertracing/all-in-one:1.51
     container_name: dispatchai-jaeger
     ports:
       - "16686:16686"  # Jaeger UI
       - "14268:14268"  # Jaeger collector
     environment:
       - COLLECTOR_OTLP_ENABLED=true
     networks:
       - dispatchai-network
   ```

3. **Instrument each service**
   
   **Add to each service's startup (app.py):**
   ```python
   from opentelemetry import trace
   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import BatchSpanProcessor
   from opentelemetry.exporter.jaeger.thrift import JaegerExporter
   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
   from opentelemetry.instrumentation.kafka import KafkaInstrumentor
   
   # Configure tracing
   trace.set_tracer_provider(TracerProvider())
   jaeger_exporter = JaegerExporter(
       agent_host_name="jaeger",
       agent_port=6831,
   )
   trace.get_tracer_provider().add_span_processor(
       BatchSpanProcessor(jaeger_exporter)
   )
   
   # Auto-instrument
   FastAPIInstrumentor.instrument_app(app)
   KafkaInstrumentor().instrument()
   ```

4. **Configure trace context propagation**
   - Automatic HTTP header propagation (W3C Trace Context)
   - Kafka message header propagation for async flows
   - Database query tracing

#### Benefits
- ✅ Automatic span creation for all HTTP requests
- ✅ Kafka message flow visualization
- ✅ Database query performance tracking
- ✅ Visual timeline replacing manual correlation ID grep
- ✅ Identifies bottlenecks in distributed workflows

#### Migration Path
OpenTelemetry automatically generates trace IDs compatible with correlation IDs. Keep existing correlation ID logging for 2 weeks during validation.

---

### Phase 3: Centralized Logging + Alerting (Priority: MEDIUM)
**Timeline:** 1-2 days  
**Effort:** Low-Medium  
**Impact:** Medium

#### Implementation Steps

1. **Add Loki + Promtail for log aggregation**
   ```yaml
   loki:
     image: grafana/loki:2.9.3
     container_name: dispatchai-loki
     ports:
       - "3100:3100"
     volumes:
       - loki_data:/loki
     command: -config.file=/etc/loki/local-config.yaml
     networks:
       - dispatchai-network
   
   promtail:
     image: grafana/promtail:2.9.3
     container_name: dispatchai-promtail
     volumes:
       - /var/lib/docker/containers:/var/lib/docker/containers:ro
       - ./promtail-config.yml:/etc/promtail/config.yml
     command: -config.file=/etc/promtail/config.yml
     depends_on:
       - loki
     networks:
       - dispatchai-network
   ```

2. **Configure Promtail to ship logs**
   ```yaml
   # promtail-config.yml
   server:
     http_listen_port: 9080
   
   clients:
     - url: http://loki:3100/loki/api/v1/push
   
   scrape_configs:
     - job_name: containers
       docker_sd_configs:
         - host: unix:///var/run/docker.sock
       relabel_configs:
         - source_labels: ['__meta_docker_container_name']
           target_label: 'container'
         - source_labels: ['__meta_docker_container_log_stream']
           target_label: 'stream'
   ```

3. **Add Alertmanager for SLO alerting**
   ```yaml
   alertmanager:
     image: prom/alertmanager:v0.26.0
     container_name: dispatchai-alertmanager
     ports:
       - "9093:9093"
     volumes:
       - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
     networks:
       - dispatchai-network
   ```

4. **Define alert rules**
   ```yaml
   # prometheus-alerts.yml
   groups:
     - name: dispatchai_slos
       interval: 30s
       rules:
         - alert: HighWebhookLatency
           expr: histogram_quantile(0.95, rate(api_request_duration_seconds_bucket{job="ingress"}[5m])) > 0.5
           for: 5m
           labels:
             severity: critical
           annotations:
             summary: "Webhook p95 latency > 500ms"
         
         - alert: HighConsumerLag
           expr: kafka_consumer_lag > 100
           for: 5m
           labels:
             severity: critical
           annotations:
             summary: "Kafka consumer lag > 100 messages"
         
         - alert: ClassificationFailureRate
           expr: rate(openai_api_errors_total[5m]) / rate(issues_processed_total[5m]) > 0.1
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "Classification error rate > 10%"
   ```

#### Benefits
- ✅ Single interface to query logs across all services
- ✅ Correlation ID filtering in Grafana UI
- ✅ Automated alerting on SLO violations
- ✅ Slack/PagerDuty/email integration
- ✅ No more manual log grepping

---

### Phase 4: Quick Wins (Immediate)
**Timeline:** 2-4 hours  
**Effort:** Low  
**Impact:** Low-Medium

These can be done before other phases while keeping the in-memory solution:

#### 1. Add Per-Endpoint Metrics
```python
# gateway/app.py
class ServiceMetrics:
    def __init__(self):
        self.endpoint_metrics = defaultdict(lambda: {
            'count': 0,
            'latencies': []
        })
    
    def record_endpoint_latency(self, endpoint: str, method: str, latency_ms: float):
        key = f"{method}:{endpoint}"
        self.endpoint_metrics[key]['count'] += 1
        self.endpoint_metrics[key]['latencies'].append(latency_ms)
```

#### 2. Add Error Rate Tracking
```python
class ServiceMetrics:
    def __init__(self):
        self.errors_by_type = Counter()
    
    def record_error(self, error_type: str):
        self.errors_by_type[error_type] += 1
```

#### 3. Add Kafka Producer Metrics
Currently only tracking consumer lag. Add:
- Messages sent to Kafka
- Producer failures
- Send latency

#### 4. Enhanced Health Check
```python
@app.get("/health/live")
async def liveness():
    """Fast liveness check (no dependency verification)"""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    """Full readiness check (with dependencies)"""
    # Existing comprehensive check
```

---

## Implementation Roadmap

### Week 1: Prometheus Foundation
- [ ] Add Prometheus + Grafana containers
- [ ] Create prometheus.yml configuration
- [ ] Add prometheus_client to all services
- [ ] Replace ServiceMetrics in gateway service
- [ ] Test metrics collection and visualization
- [ ] Create initial Grafana dashboard

### Week 2: Full Metrics Migration
- [ ] Replace ServiceMetrics in classifier service
- [ ] Add metrics to ingress service
- [ ] Create service-specific Grafana dashboards
- [ ] Create SLO compliance dashboard
- [ ] Validate metrics against old system
- [ ] Remove old ServiceMetrics classes

### Week 3: Distributed Tracing
- [ ] Add OpenTelemetry dependencies
- [ ] Add Jaeger container
- [ ] Instrument gateway service
- [ ] Instrument classifier service
- [ ] Instrument ingress service
- [ ] Configure Kafka trace propagation
- [ ] Validate E2E trace visibility

### Week 4: Logging + Alerting
- [ ] Add Loki + Promtail containers
- [ ] Configure log shipping
- [ ] Add Loki data source to Grafana
- [ ] Create log exploration dashboard
- [ ] Add Alertmanager container
- [ ] Define alert rules for SLOs
- [ ] Configure notification channels
- [ ] Test alerting with simulated issues

---

## Data Persistence Strategy

### Development Environment
**Recommendation:** Self-hosted (local Docker volumes)

```yaml
volumes:
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
  loki_data:
    driver: local
```

**Retention:**
- Prometheus: 30 days
- Loki: 14 days
- Grafana: Unlimited (dashboards/configs only)

**Cost:** Free

### Production Environment
**Recommendation:** Hybrid approach

**Option A: Self-Hosted**
- Run full stack on VPS
- Use persistent volumes
- Set up backup strategy
- **Cost:** $0 (using existing infrastructure)

**Option B: Grafana Cloud (Recommended)**
- Use Grafana Cloud free tier
- Remote write from self-hosted Prometheus
- Keep local Prometheus for fast queries
- **Cost:** Free up to 10k series, 50GB logs, 14-day retention
- **Upgrade path:** $49/mo for unlimited

**Option C: Fully Managed**
- AWS Managed Prometheus + Grafana
- **Cost:** ~$50-100/mo at current scale

---

## Expected Outcomes

### Metrics Improvements
| Metric | Current | After Phase 1 | After Phase 2 |
|--------|---------|---------------|---------------|
| **Metrics Persistence** | None (lost on restart) | 30 days | 30 days |
| **Visualization** | Manual curl + jq | Grafana dashboards | Grafana dashboards |
| **Historical Analysis** | Not possible | ✅ Full history | ✅ Full history |
| **Trace Visibility** | Manual log grep | Manual log grep | Visual timeline |
| **Alerting** | None | Manual rules | Automated |
| **Time to Debug Issue** | 10-15 minutes | 5 minutes | 2 minutes |

### Developer Experience
- **Before:** `curl localhost:8002/metrics | jq`
- **After Phase 1:** Open Grafana dashboard
- **After Phase 2:** Click trace ID in logs → Visual timeline in Jaeger

### Production Readiness
- **Before:** Missing critical observability for production
- **After:** Industry-standard tooling used by Fortune 500 companies

---

## Migration Risks & Mitigation

### Risk 1: Existing metrics endpoints break
**Mitigation:** Keep old `/metrics` endpoints during transition, deprecate after validation

### Risk 2: Performance impact from instrumentation
**Mitigation:** OpenTelemetry adds <1ms overhead, negligible for current workload

### Risk 3: Increased infrastructure complexity
**Mitigation:** All services containerized, single `docker-compose up` command

### Risk 4: Storage requirements
**Mitigation:** 
- Prometheus: ~50MB/day at current scale
- Loki: ~100MB/day for logs
- Total: ~5GB/month (trivial for modern systems)

---

## Success Criteria

### Phase 1 Complete When:
- [ ] All services expose Prometheus metrics
- [ ] Grafana dashboards show real-time data
- [ ] Can query historical metrics from last 30 days
- [ ] Latency percentiles match old system (validation)

### Phase 2 Complete When:
- [ ] Can view E2E trace for any request in Jaeger
- [ ] Kafka message flow visible in traces
- [ ] Database queries show up in traces
- [ ] Identify slowest operation in <30 seconds

### Phase 3 Complete When:
- [ ] Can query logs from all services in one interface
- [ ] Alerts fire when SLOs violated
- [ ] Alert notifications received (Slack/email)
- [ ] No manual log grepping needed for debugging

---

## Documentation Updates Required

After implementation, update these files:
- `OBSERVABILITY_GUIDE.md` - Add Prometheus/Grafana/Jaeger sections
- `DEVELOPMENT.md` - Add new service URLs (Grafana, Jaeger, Prometheus)
- `README.md` - Update observability features section
- `PRODUCTION_DOCKER_DEPLOYMENT.md` - Add production configuration examples

---

## Cost Summary

### Development
- **Current:** $0
- **After implementation:** $0 (all self-hosted)

### Production (Monthly)
- **Option 1 (Self-hosted):** $0 (uses existing VPS)
- **Option 2 (Grafana Cloud Free):** $0 (within limits)
- **Option 3 (Grafana Cloud Paid):** $49/mo
- **Option 4 (AWS Managed):** $50-100/mo

**Recommendation:** Start with self-hosted or Grafana Cloud free tier

---

## Next Steps

1. Review this plan with team
2. Get approval for Phase 1 timeline
3. Create feature branch: `feature/observability-improvements`
4. Begin Phase 1 implementation
5. Schedule demo after Phase 1 completion

---

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Grafana Loki](https://grafana.com/docs/loki/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)

---

*Document created: 2025-10-16*  
*Author: DispatchAI Development Team*
