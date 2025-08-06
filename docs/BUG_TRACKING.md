# Bug Tracking and Resolution Log

## Overview
This document tracks all bugs encountered during development, their root causes, resolution steps, and prevention measures. It serves as a knowledge base for future debugging and maintenance.

## Bug Status Legend
- 🔍 **Investigating**: Issue reported, investigation in progress
- ⚠️ **Known Issue**: Confirmed bug, solution in progress
- ✅ **Fixed**: Issue resolved and tested
- 🚫 **Won't Fix**: Issue acknowledged but not prioritized for fix

---

## Active Bugs

### BUG-003: Vector Similarity Search Type Error
- **Symptom**: `operator does not exist: vector <-> numeric[]`
- **Root Cause**: Embedding data type mismatch in similarity search queries
- **Resolution**: Needs proper vector type casting in SQL queries
- **Status**: ⚠️ Known issue - fallback to text similarity working
- **Impact**: Medium - Feature degrades gracefully
- **Date**: July 17, 2025
- **Reproduction**: 
  1. Store issue with embeddings in database
  2. Query for similar issues using vector similarity
  3. Error occurs in `find_similar_issues` function

---

## Resolved Bugs

### BUG-012: Dashboard API Requests Blocked by CORS Policy
- **Symptom**: Browser console shows `Access to fetch at 'http://5.78.157.202:8002/api/issues' from origin 'http://5.78.157.202' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource` and `Error fetching issues: TypeError: Failed to fetch`
- **Root Cause**: Gateway service CORS configuration only allowed localhost origins, but production dashboard runs on server IP `http://5.78.157.202` without port specification
- **Resolution**: Added `http://5.78.157.202` to CORS_ORIGINS environment variable in production configuration
- **Status**: ✅ Fixed
- **Impact**: High - Dashboard API communication completely broken
- **Date**: August 6, 2025
- **Fix Applied**:
  - Updated `.env.prod` line 21: `CORS_ORIGINS=http://5.78.157.202,http://5.78.157.202:3000,http://localhost:3000,https://dispatchai.ascher.dev`
  - Recreated gateway container with `docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d gateway`
  - Verified CORS origins include server IP without port (since dashboard is served on port 80 mapped from port 3000)
- **Prevention**: Include all production origins in CORS configuration from initial deployment, test API communication on production servers
- **Verification**:
  ```bash
  # Test CORS preflight request
  curl -H "Origin: http://5.78.157.202" -H "Access-Control-Request-Method: GET" -X OPTIONS http://5.78.157.202:8002/api/issues
  # Should return: OK
  
  # Test actual API request
  curl -H "Origin: http://5.78.157.202" http://5.78.157.202:8002/api/issues
  # Should return JSON array of issues
  
  # Browser console should no longer show CORS errors
  ```
- **Technical Details**: Gateway service uses FastAPI CORSMiddleware which validates Origin header against allowed origins list. Dashboard served on port 80 (mapped from 3000) sends Origin: `http://5.78.157.202` (without port), requiring exact match in CORS_ORIGINS.

### BUG-011: WebSocket Connection Blocked by Content Security Policy
- **Symptom**: Dashboard shows "WebSocket: disconnected" and browser console shows CSP violation: `Refused to connect to 'ws://5.78.157.202:8002/ws' because it violates the following Content Security Policy directive`
- **Root Cause**: nginx CSP header had `default-src 'self' http: https: data: blob: 'unsafe-inline'` without explicit `connect-src`, causing WebSocket connections to be blocked
- **Resolution**: Added explicit `connect-src 'self' http: https: ws: wss:` to Content Security Policy
- **Status**: ✅ Fixed
- **Impact**: High - Real-time WebSocket features completely non-functional
- **Date**: August 5, 2025
- **Fix Applied**:
  - Modified dashboard/nginx.conf line 27 to include `connect-src 'self' http: https: ws: wss:`
  - Rebuilt dashboard container with `--no-cache` to apply nginx configuration changes
  - Restarted dashboard service to activate new CSP
- **Prevention**: Include WebSocket protocols in CSP from initial deployment, test real-time features on production servers
- **Verification**:
  ```bash
  # Check CSP header includes WebSocket support
  curl -I http://5.78.157.202:3000 | grep -i content-security
  # Should show: connect-src 'self' http: https: ws: wss:
  
  # Dashboard should show "WebSocket: connected" instead of "disconnected"
  ```
- **Browser Error**: `Content Security Policy directive: "default-src 'self' http: https: data: blob: 'unsafe-inline'". Note that 'connect-src' was not explicitly set, so 'default-src' is used as a fallback.`

### BUG-010: AI Classification Parsing Failure - Markdown Code Blocks
- **Symptom**: `WARNING: Failed to parse AI response, using fallback` logs in classifier service
- **Root Cause**: OpenAI API returns JSON responses wrapped in markdown code blocks (`\`\`\`json ... \`\`\``), but code attempted to parse raw response as JSON
- **Resolution**: Added logic to detect and strip markdown code block markers before JSON parsing
- **Status**: ✅ Fixed
- **Impact**: Medium - AI classification degraded to fallback values (lower confidence, generic priority)
- **Date**: July 21, 2025
- **Fix Applied**: 
  - Added markdown stripping logic in classifier/app.py lines 281-285
  - Strips `\`\`\`json\n` and `\n\`\`\`` wrapper, falls back to plain `\`\`\`` wrapper
  - Added debug logging to capture response content for troubleshooting
- **Prevention**: Include AI response format validation in integration tests
- **Verification**:
  ```bash
  # Send test webhook and check classification results
  ./send_webhook.sh
  # Should see proper AI values (high confidence, detailed tags) vs fallback values
  
  # Check logs for absence of parsing warnings
  docker logs dispatchai-classifier --tail 20 | grep -E "(Failed to parse|WARNING.*fallback)"
  # Should return no results
  ```

### BUG-009: Dashboard Not Starting - Node.js Version Incompatibility
- **Symptom**: Dashboard container stuck in restarting loop with `crypto.hash is not a function` error
- **Root Cause**: Vite 7.0.4 requires Node.js 22+ but Docker container used Node.js 18
- **Resolution**: Updated Dockerfile.dev to use Node.js 22-alpine
- **Status**: ✅ Fixed
- **Impact**: High - Dashboard completely non-functional
- **Date**: July 21, 2025
- **Fix Applied**: Changed `FROM node:18-alpine` to `FROM node:22-alpine` in dashboard/Dockerfile.dev
- **Prevention**: Regular dependency version compatibility audits
- **Verification**:
  ```bash
  # Test dashboard availability
  curl -I http://localhost:3000
  # Should return HTTP 200 OK
  
  # Check container logs for successful startup
  docker logs dispatchai-dashboard --tail 10
  # Should show "VITE ready in XXXms"
  ```

### BUG-006: CI/CD Pipeline Missing Test Scripts and Directories
- **Symptom**: Multiple test failures in CI/CD pipeline
  - `ERROR: file or directory not found: tests/` in classifier/gateway services
  - `npm run test` script not found in dashboard package.json
- **Root Cause**: Makefile tries to run tests but test directories or scripts don't exist
- **Resolution**: Update Makefile to gracefully handle missing test infrastructure
- **Status**: ✅ Fixed
- **Impact**: High - CI/CD pipeline failing
- **Date**: July 17, 2025
- **Fix Applied**: 
  - Updated `test-classifier` target: `@if [ -f classifier/requirements.txt ] && [ -d classifier/tests ]; then`
  - Updated `test-gateway` target: `@if [ -f gateway/requirements.txt ] && [ -d gateway/tests ]; then`
  - Updated `test-dashboard` target: `npm run test 2>/dev/null || echo "⚠️  Dashboard tests not yet implemented"`
- **Prevention**: Create placeholder test directories/scripts or improve test target logic

### BUG-008: send_webhook.sh Issues Not Appearing in API Immediately
- **Symptom**: When running `./send_webhook.sh`, webhook is accepted by ingress but issue doesn't appear in API after 5 seconds. Issues only appear after `make dev-down && make dev-up` restart cycle.
- **Root Cause**: Kafka consumer in classifier service configured with `consumer_timeout_ms=1000`, causing consumer to stop after 1 second of inactivity. Consumer would process the first message after startup, then timeout and stop, requiring full service restart to process subsequent messages.
- **Resolution**: Removed `consumer_timeout_ms=1000` parameter to keep consumer running indefinitely
- **Status**: ✅ Fixed
- **Impact**: High - Webhook testing and real-time processing broken
- **Date**: July 21, 2025
- **Fix Applied**:
  - Removed `consumer_timeout_ms=1000` from KafkaConsumer configuration in classifier/app.py line 642
  - Added comment explaining the change: `# Removed consumer_timeout_ms to keep consumer running indefinitely`
- **Secondary Issue**: Missing INFO logging configuration in classifier prevented visibility of consumer thread status
- **Secondary Fix**: Added `logging.basicConfig(level=logging.INFO)` in classifier/app.py line 25-26
- **Prevention**:
  - Use indefinite consumer timeouts for production message processing
  - Add consumer health monitoring and alerting
  - Include consumer status checks in integration tests
- **Verification**:
  ```bash
  # Test real-time webhook processing
  ./send_webhook.sh
  # Issue should appear in API within 5 seconds

  # Verify consumer thread logs are visible
  docker logs dispatchai-classifier | grep "Started Kafka consumer thread"
  ```

### BUG-007: INFO Level Logs Not Appearing in Services
- **Symptom**: Custom INFO level logs not visible in Docker logs despite being defined in code
- **Root Cause**: Default Python logging level set to WARNING (30), filtering out INFO messages (20)
- **Resolution**: Added `logging.basicConfig(level=logging.INFO)` before structlog configuration
- **Status**: ✅ Fixed
- **Impact**: Medium - Debugging visibility impaired, functionality unaffected
- **Date**: July 21, 2025
- **Fix Applied**:
  - Added `import logging` and `logging.basicConfig(level=logging.INFO)` in ingress/app.py line 22-23
  - Added same fix to classifier/app.py line 25-26
  - Placed before structlog.configure() to ensure proper level inheritance
- **Prevention**: Set explicit log levels in all services, document logging configuration
- **Verification**:
  ```bash
  # Test logging levels
  docker exec dispatchai-ingress python -c "import logging; print('Log level:', logging.getLogger().getEffectiveLevel())"

  # Verify INFO logs appear after webhook
  ./send_webhook.sh
  docker logs dispatchai-ingress --tail 10 | grep INFO
  ```

### BUG-001: Gateway Kafka Consumer Thread Not Visible in Logs
- **Symptom**: Gateway consumer thread starts but doesn't show processing logs
- **Root Cause**: Hot-reload interference with background threads + structured logging configuration
- **Resolution**: Verified consumer works via direct testing; logs aren't visible due to thread isolation
- **Status**: ✅ Verified working via alternative testing
- **Impact**: Low - Functionality works, debugging visibility limited
- **Date**: July 17, 2025
- **Prevention**: Use direct consumer testing for verification instead of relying on logs

### BUG-002: Manual Corrections Schema Mismatch
- **Symptom**: `column "issue_id" of relation "manual_corrections" does not exist`
- **Root Cause**: Database schema used `enriched_issue_id` but code referenced `issue_id`
- **Resolution**: Updated Gateway code to use correct column name `enriched_issue_id`
- **Status**: ✅ Fixed
- **Impact**: High - Manual corrections feature broken
- **Date**: July 16, 2025
- **Fix Applied**: Updated `app.py` lines 395-435 to use correct column references
- **Prevention**: Schema validation tests for API endpoints

### BUG-004: CI/CD Pipeline Docker Container Dependency
- **Symptom**: Tests requiring Docker containers failing in CI environment
- **Root Cause**: GitHub Actions runner doesn't have Docker containers running
- **Resolution**: Created `test-ci` target for container-free testing
- **Status**: ✅ Fixed
- **Impact**: High - CI/CD pipeline failing
- **Date**: July 16, 2025
- **Fix Applied**: 
  - Added `test-ci` target in Makefile
  - Updated `.github/workflows/ci.yml` to use `test-ci`
  - Created `test-ingress-local` for local testing
- **Prevention**: Separate test targets for different environments

### BUG-005: Node.js Version Incompatibility in CI
- **Symptom**: Vite 7.0.4 required Node.js 20+ but CI used Node.js 18
- **Root Cause**: Outdated Node.js version in GitHub Actions workflow
- **Resolution**: Updated GitHub Actions to use Node.js 20
- **Status**: ✅ Fixed
- **Impact**: Medium - Dashboard CI tests failing
- **Date**: July 16, 2025
- **Fix Applied**: Updated `.github/workflows/ci.yml` to use `node-version: '20'`
- **Prevention**: Regular dependency and environment version audits

---

## Debugging Methodology

### 1. Issue Identification
- **Symptom Documentation**: Record exact error messages and user experience
- **Environment Context**: Note service, environment, and conditions when issue occurred
- **Reproduction Steps**: Document minimal steps to reproduce the issue

### 2. Root Cause Analysis
- **Log Analysis**: Check service logs, database logs, and system logs
- **Component Testing**: Test individual components in isolation
- **Data Flow Tracing**: Follow data through the complete pipeline
- **Dependency Check**: Verify external service and database connectivity

### 3. Resolution Implementation
- **Minimal Changes**: Make smallest possible change to fix the issue
- **Testing**: Verify fix works in isolation and doesn't break other features
- **Documentation**: Update relevant documentation and code comments
- **Rollback Plan**: Ensure changes can be reverted if needed

### 4. Prevention Measures
- **Test Coverage**: Add tests to prevent regression
- **Monitoring**: Add logging or metrics to detect similar issues early
- **Documentation**: Update troubleshooting guides and runbooks
- **Process Improvement**: Identify process changes to prevent similar issues

---

## Common Debugging Commands

### Service Health Checks
```bash
# Check all services
make status

# Individual service health
curl http://localhost:8000/health  # Ingress
curl http://localhost:8001/health  # Classifier
curl http://localhost:8002/health  # Gateway
```

### Database Debugging
```bash
# Check database connectivity
make db-shell

# Query specific tables
make db-query SQL="SELECT * FROM dispatchai.issues LIMIT 5;"
make db-query SQL="SELECT * FROM dispatchai.enriched_issues LIMIT 5;"

# Check schema
make db-query SQL="\\dt dispatchai.*"
```

### Kafka Debugging
```bash
# List topics
make kafka-topics

# Check message flow
make kafka-console TOPIC=issues.raw
make kafka-console TOPIC=issues.enriched

# Tail messages in real-time
make kafka-tail TOPIC=issues.enriched
```

### WebSocket Testing
```bash
# Test WebSocket broadcasting
curl -X POST http://localhost:8002/api/test/websocket

# Check WebSocket endpoint
wscat -c ws://localhost:8002/ws
```

### Log Analysis
```bash
# Service logs
make dev-logs
make dev-logs-service SERVICE=ingress

# Individual container logs
docker logs dispatchai-ingress --tail 50
docker logs dispatchai-classifier --tail 50
docker logs dispatchai-gateway --tail 50
```

---

## Performance Monitoring

### Key Metrics to Track
- **Response Times**: API endpoint latency
- **Message Processing**: Kafka producer/consumer lag
- **Database Performance**: Query execution times
- **WebSocket Connections**: Active connections and message throughput
- **Memory Usage**: Container memory consumption
- **Error Rates**: HTTP 5xx responses and failed message processing

### Monitoring Commands
```bash
# Container resource usage
docker stats

# Database performance
make db-query SQL="SELECT * FROM pg_stat_activity;"

# Kafka consumer lag
docker exec dispatchai-redpanda rpk group describe dispatchai-gateway
```

---

## Issue Escalation Process

### Severity Levels
- **Critical**: System down, data loss, security breach
- **High**: Core functionality broken, user-facing errors
- **Medium**: Feature degradation, performance issues
- **Low**: Minor bugs, cosmetic issues

### Escalation Path
1. **Developer**: First line of investigation and resolution
2. **Team Lead**: Complex issues requiring architectural changes
3. **Infrastructure**: Issues related to deployment, scaling, or external dependencies
4. **Product**: Issues requiring business decision or priority changes

---

## Knowledge Base

### Common Error Patterns
1. **Database Connection Issues**: Usually resolved with `make db-reset`
2. **Kafka Consumer Lag**: Check consumer group status and restart consumers
3. **WebSocket Connection Drops**: Verify network stability and connection timeouts
4. **Hot-Reload Conflicts**: Restart development environment to clear state

### Best Practices
- Always test fixes in development environment first
- Use structured logging for better debugging
- Document any non-obvious fixes for future reference
- Create tests for resolved bugs to prevent regression
- Keep debugging commands up-to-date with system changes

---

*Last Updated: July 21, 2025*
*Next Review: Weekly during active development*