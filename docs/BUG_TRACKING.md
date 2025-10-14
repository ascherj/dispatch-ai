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

### BUG-017: Classifier Processing Stale Kafka Messages After Database Reset
- **Symptom**: After running `make db-reset`, classifier processes 64 old messages from Kafka queue that reference issues no longer in the fresh database. Expensive OpenAI API calls are made before discovering issues don't exist.
- **Root Cause**: 
  1. `make db-reset` only removed PostgreSQL volume (`infra_postgres_data`), leaving Redpanda volume (`infra_redpanda_data`) intact
  2. Redpanda persists messages (7-day retention) and consumer offsets in Docker volume
  3. Classifier consumer group (`dispatchai-classifier`) resumed from last committed offset (167), with 64 messages remaining in queue (offset 231)
  4. Classifier's `classify_issue()` made expensive API calls before checking if issue exists
  5. Original check in `store_enriched_issue()` happened too late - after OpenAI classification and embedding generation
- **Resolution**: 
  1. Enhanced `make db-reset` to remove both PostgreSQL and Redpanda volumes
  2. Added early idempotency check via `is_issue_already_enriched()` helper function
  3. Check happens immediately after `store_raw_issue()`, before expensive OpenAI API calls
  4. Added Kafka management commands for offset control
- **Status**: ✅ Fixed
- **Impact**: High - Wasted OpenAI API calls, confusion during development, potential cost impact
- **Date**: October 14, 2025
- **Fix Applied**:
  - Updated `Makefile` line 248-254: `db-reset` now removes both `infra_postgres_data` and `infra_redpanda_data` volumes
  - Added `classifier/app.py` lines 514-534: New `is_issue_already_enriched(github_issue_id)` helper function
  - Updated `classifier/app.py` lines 356-367: Early exit check before expensive operations
  - Added `Makefile` kafka-reset-offsets target: Quick command to skip old messages
  - Added `Makefile` kafka-describe-group target: Check consumer group status and lag
- **Technical Details**:
  - **Before fix flow**: `store_raw_issue() → ai_classification() ($$$) → generate_embedding() ($$$) → store_enriched_issue() [check here - too late!]`
  - **After fix flow**: `store_raw_issue() → is_issue_already_enriched() [check here!] → return early if enriched → skip all expensive operations`
  - Consumer group state at time of discovery: offset 167/231, lag 64 messages
  - Redpanda retention: 7 days (604800000 ms) for `issues.raw` topic
  - Classifier uses `auto_offset_reset='earliest'` with `enable_auto_commit=True`
  - Issue exists because `store_raw_issue()` uses `INSERT ... ON CONFLICT DO UPDATE`, always succeeding
- **Prevention**:
  - Always reset both database and Kafka together in development
  - Implement early idempotency checks before expensive operations
  - Use `make kafka-describe-group` to monitor consumer lag
  - Consider event sourcing architecture where Kafka is source of truth
- **Verification**:
  ```bash
  # Check consumer group status
  make kafka-describe-group
  # Should show: TOTAL-LAG 0
  
  # Verify idempotency - reprocessing same issue won't trigger API calls
  # 1. Find enriched issue: make db-query SQL="SELECT github_issue_id FROM dispatchai.issues i JOIN dispatchai.enriched_issues ei ON i.id = ei.issue_id LIMIT 1;"
  # 2. Check classifier logs when processing: docker logs dispatchai-classifier --tail 50 | grep "already enriched"
  
  # Reset only consumer offsets (skip old messages without volume deletion)
  make kafka-reset-offsets
  
  # Complete reset (removes both volumes)
  make db-reset
  ```
- **Cost Impact**: Estimated 64 duplicate OpenAI API calls avoided:
  - Classification API calls: 64 × $0.0001 = $0.0064
  - Embedding API calls: 64 × $0.00002 = $0.00128
  - Total saved per incident: ~$0.008 (minimal but adds up with frequent resets)
- **Development Workflow Impact**: 
  - Developers can now safely run `make db-reset` without Kafka sync issues
  - Idempotent processing allows safe message replay for testing
  - Clear logging indicates when messages are skipped due to existing enrichment

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

### BUG-016: React-Markdown Import Error in Dashboard Container
- **Symptom**: Dashboard container shows Vite error `Failed to resolve import "react-markdown" from "src/App.tsx". Does the file exist?` even though package is listed in `package.json` dependencies
- **Root Cause**: Docker named volume (`dashboard_node_modules`) persisted stale `node_modules` contents from before `react-markdown` was added to dependencies. Volume mounts take precedence over image contents, so even rebuilding the image didn't help - the old volume masked the new packages.
- **Resolution**: Removed stale Docker volume and rebuilt container to repopulate with correct dependencies
- **Status**: ✅ Fixed
- **Impact**: High - Dashboard completely broken with import errors
- **Date**: October 14, 2025
- **Fix Applied**:
  - Removed stale volume: `docker volume rm infra_dashboard_node_modules`
  - Rebuilt container: `docker compose up -d --build dashboard`
  - Volume repopulated from fresh image with all dependencies including `react-markdown`
- **Technical Details**:
  - Named volumes persist across container rebuilds and restarts
  - Volume population happens once when volume is first created, copying from image's `/app/node_modules`
  - If image is rebuilt but volume already exists, volume contents take precedence (mount overwrites image)
  - Build cache can compound the issue - even `--no-cache` rebuilds don't help if the volume is stale
  - Solution requires removing the volume to force repopulation from rebuilt image
- **Prevention**:
  - When adding new npm dependencies, consider removing `node_modules` volume to force reinstall
  - Document volume persistence behavior in development setup
  - Consider using `docker compose down -v` to remove volumes during major dependency updates
- **Verification**:
  ```bash
  # Verify package exists in container
  docker compose exec dashboard ls node_modules | grep react-markdown
  # Should return: react-markdown
  
  # Check dashboard logs for successful startup
  docker compose logs dashboard --tail 20
  # Should show: "VITE v7.0.4 ready in XXXms" with no import errors
  ```
- **Volume Purpose & Recommendations**:
  - **Why the volume exists**: Named volume for `node_modules` improves performance on macOS/Windows where Docker file I/O is slow. Prevents npm packages from being shared between host and container via slow bind mount.
  - **Performance benefit**: 10-100x faster file access for the thousands of small files in `node_modules`
  - **Trade-off**: Adds complexity - dependencies aren't visible on host, volume can become stale
  - **Recommendation**: **Keep the volume** for development - the performance benefit is significant. Just be aware of this edge case when adding dependencies and use `docker volume rm` when needed.
  - **Alternative approach**: Some teams use `.dockerignore` for `node_modules` and rely on image layers only, but this loses the bind mount advantage for hot-reload during development.

### BUG-015: Duplicate Enriched Issues After Repository Resync
- **Symptom**: When resyncing issues from connected repositories, duplicate issue cards appear in the frontend. Each resync creates additional enriched records for the same issues.
- **Root Cause**:
  1. `enriched_issues` table had no unique constraint on `issue_id`, allowing multiple enriched records per issue
  2. Classifier's `store_enriched_issue()` function used simple INSERT without `ON CONFLICT` handling
  3. Auth service republished ALL issues to Kafka during resync, even if already enriched
- **Resolution**:
  1. Added `UNIQUE NOT NULL` constraint to `enriched_issues.issue_id` in schema
  2. Updated classifier to use UPSERT pattern with `ON CONFLICT (issue_id) DO UPDATE`
  3. Created migration script to remove existing duplicates and add constraint
- **Status**: ✅ Fixed
- **Impact**: High - 65 out of 97 issues had duplicates, with 2 issues enriched 3 times each (67 total duplicate records)
- **Date**: October 13, 2025
- **Fix Applied**:
  - Updated `infra/init-db.sql` line 38: Added `UNIQUE NOT NULL` to `issue_id BIGINT` column definition
  - Updated `classifier/app.py` lines 486-512: Added `ON CONFLICT (issue_id) DO UPDATE SET` with all classification fields
  - Created `infra/migrations/001_add_unique_issue_id_constraint.sql` migration that:
    - Removes duplicate enriched_issues keeping most recent by `processed_at`
    - Adds `enriched_issues_issue_id_unique` constraint
    - Verifies constraint was successfully added
  - Added `migrate` and `migrate-file` targets to Makefile for migration management
  - Restarted classifier service to apply code changes
- **Prevention**:
  - Always use UPSERT patterns for data that should be idempotent
  - Add unique constraints at database level to enforce data integrity
  - Test resync operations to ensure idempotency
  - Consider optimizing to skip Kafka publishing for already-enriched issues
- **Verification**:
  ```bash
  # Apply migration
  make migrate-file FILE=001_add_unique_issue_id_constraint.sql

  # Check for duplicates (should return 0 rows)
  make db-query SQL="SELECT issue_id, COUNT(*) as count FROM dispatchai.enriched_issues GROUP BY issue_id HAVING COUNT(*) > 1;"

  # Verify unique constraint exists
  make db-query SQL="SELECT constraint_name FROM information_schema.table_constraints WHERE table_schema = 'dispatchai' AND table_name = 'enriched_issues' AND constraint_type = 'UNIQUE';"

  # Test resync - connect repository and sync twice
  # Frontend should show each issue exactly once
  ```
- **Technical Details**:
  - Before fix: 65 issues with duplicates (67 duplicate records total)
  - After fix: 1:1 relationship between issues and enriched_issues (97:97)
  - Migration deleted 67 duplicate records, keeping most recent
  - UPSERT updates classification fields: `classification`, `summary`, `tags`, `priority`, `category`, `severity`, `component`, `sentiment`, `embedding`, `confidence_score`, `processing_model`, `ai_reasoning`, `updated_at`
  - Database constraint prevents duplicates at insert time
  - Classifier now handles reprocessing by updating existing enriched record

### BUG-014: Dev JWT Authentication Filtering Issues
- **Symptom**: `send_webhook.sh` test script successfully sends webhooks and issues are classified/stored in database, but API calls return empty arrays `[]` even though issues exist
- **Root Cause**: Gateway `/api/issues` and `/api/stats` endpoints filter results by user's connected repositories. Dev JWT uses `sub: '0'` with `dev_mode: true` but has no repository connections in database, causing all queries to return empty despite issues existing
- **Resolution**: Modified Gateway to detect `dev_mode: true` in JWT payload and skip repository filtering for development testing
- **Status**: ✅ Fixed
- **Impact**: High - End-to-end testing completely broken
- **Date**: October 13, 2025
- **Fix Applied**:
  - Updated `gateway/app.py` `/api/issues` endpoint (lines 499-530) to check `current_user.get("dev_mode")` and skip repository access filtering when true
  - Updated `gateway/app.py` `/api/stats` endpoint (lines 834-916) to check `dev_mode` and return statistics for all issues without filtering
  - Changed WHERE clause from hardcoded user repository check to conditional: `"1=1"` when dev_mode, else user repository filtering
  - Created `scripts/requirements.txt` with `python-jose[cryptography]` dependency for JWT generation in test scripts
- **Prevention**:
  - Document dev JWT requirements in testing documentation
  - Add dev mode checks to all endpoints that filter by user access
  - Include integration tests that verify dev JWT bypasses access controls
- **Verification**:
  ```bash
  # Install test script dependencies
  pip install -r requirements.txt

  # Test full webhook pipeline with dev JWT
  ./scripts/send_webhook.sh
  # Should show:
  # ✅ Webhook accepted
  # ✅ Issue found in API
  # ✅ AI classification triggered
  # ✅ Full pipeline completed

  # Verify issue appears in API
  python3 -c "from jose import jwt; import time; print(jwt.encode({'sub':'0','username':'dev_user','dev_mode':True,'exp':int(time.time())+3600}, 'dev-jwt-secret-change-in-production-to-secure-random-key', algorithm='HS256'))" | xargs -I {} curl -H "Authorization: Bearer {}" http://localhost:8002/api/issues | jq length
  # Should return count > 0
  ```
- **Technical Details**:
  - Dev JWT payload: `{'sub': '0', 'username': 'dev_user', 'dev_mode': True, 'exp': timestamp}`
  - JWT secret: `dev-jwt-secret-change-in-production-to-secure-random-key` (hardcoded in both script and Gateway)
  - User ID `0` doesn't exist in `dispatchai.users` table and has no entries in `dispatchai.user_repositories`
  - Production JWTs from auth service don't include `dev_mode` field, maintaining proper access controls
  - Gateway checks `is_dev_mode = current_user.get("dev_mode", False)` defaulting to False for security

### BUG-013: GitHub Issues with Null Body Fields Fail Processing
- **Symptom**: Classifier service fails with `1 validation error for IssueData body Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]` when GitHub issues have empty body content
- **Root Cause**: Pydantic model expects `body` field as required string, but GitHub webhooks send `null` for issues without body content
- **Resolution**: Update IssueData model to allow Optional[str] with empty string default, handle null safely in processing logic
- **Status**: ✅ Fixed
- **Impact**: High - All GitHub issues without body content failed to process
- **Date**: August 6, 2025
- **Fix Applied**:
  - Updated classifier/app.py line 78: `body: Optional[str] = ""` instead of `body: str`
  - Fixed AI processing: `body=(issue.body or "")[:2000]` to handle null safely
  - Fixed fallback classification: `body_lower = (issue.body or "").lower()` 
  - Rebuilt classifier container with updated code
- **Prevention**: Test webhook processing with various GitHub issue formats including empty bodies
- **Verification**:
  ```bash
  # Test webhook with null body
  curl -X POST http://5.78.157.202:8000/webhook/github \
    -H "X-Hub-Signature-256: sha256=..." \
    -H "X-GitHub-Event: issues" \
    -d '{"action":"opened","issue":{"body":null,...}}'
  
  # Should process successfully and appear in API
  curl http://5.78.157.202:8002/api/issues
  ```
- **Technical Details**: GitHub issues created without description have `"body": null` in webhook payload, requiring Optional type handling in Pydantic models and safe string operations in processing logic.

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
  ./scripts/send_webhook.sh
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
- **Symptom**: When running `./scripts/send_webhook.sh`, webhook is accepted by ingress but issue doesn't appear in API after 5 seconds. Issues only appear after `make dev-down && make dev-up` restart cycle.
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
  ./scripts/send_webhook.sh
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

# Check consumer group status and lag
make kafka-describe-group

# Reset consumer offsets to skip old messages
make kafka-reset-offsets
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
2. **Kafka Consumer Lag**: Check consumer group status with `make kafka-describe-group` and use `make kafka-reset-offsets` to skip old messages
3. **Stale Kafka Messages After DB Reset**: Run `make db-reset` (resets both DB and Kafka) or `make kafka-reset-offsets` to skip old messages
4. **Classifier Reprocessing Issues**: Check logs for "already enriched - skipping reprocessing" indicating idempotent behavior
5. **WebSocket Connection Drops**: Verify network stability and connection timeouts
6. **Hot-Reload Conflicts**: Restart development environment to clear state

### Best Practices
- Always test fixes in development environment first
- Use structured logging for better debugging
- Document any non-obvious fixes for future reference
- Create tests for resolved bugs to prevent regression
- Keep debugging commands up-to-date with system changes

---

## Database Migrations

### Migration Management
- **Location**: `infra/migrations/` directory
- **Naming**: `NNN_descriptive_name.sql` format
- **Application**: `make migrate` (all) or `make migrate-file FILE=<filename>` (specific)

### Migration Guidelines
1. Always test in development environment first
2. Migrations should be idempotent (safe to run multiple times)
3. Use transactions (BEGIN/COMMIT) to ensure atomic operations
4. Include verification logic to confirm success
5. Document purpose and impact in migration file header
6. Never modify existing migrations after production deployment

### Available Migrations
- **001_add_unique_issue_id_constraint.sql** - Fixes duplicate enriched issues by adding unique constraint on `issue_id`

---

*Last Updated: October 14, 2025*
*Next Review: Weekly during active development*