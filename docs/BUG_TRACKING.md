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
make db-query SQL="SELECT * FROM auto_triager.issues LIMIT 5;"
make db-query SQL="SELECT * FROM auto_triager.enriched_issues LIMIT 5;"

# Check schema
make db-query SQL="\\dt auto_triager.*"
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
docker logs auto-triager-ingress --tail 50
docker logs auto-triager-classifier --tail 50
docker logs auto-triager-gateway --tail 50
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
docker exec auto-triager-redpanda rpk group describe auto-triager-gateway
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

*Last Updated: July 17, 2025*
*Next Review: Weekly during active development*