# Test Scripts

This directory contains scripts for testing and managing the DispatchAI system.

**All scripts should be run from the project root directory.**

## Setup

### First-time setup:

```bash
# From project root (/Users/jake/code/dispatch-ai/)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running tests:

```bash
# Activate virtual environment (if not already active)
source venv/bin/activate

# Ensure services are running
make dev

# Run any test script from project root
./scripts/send_webhook.sh
./scripts/test-correlation-tracing.sh
```

---

## Test Scripts

### `send_webhook.sh` - End-to-End Webhook Test

End-to-end test script that validates the complete issue processing pipeline.

**What it does:**
1. Generates a development JWT token
2. Sends a test GitHub webhook to the ingress service
3. Waits for the issue to be processed and stored
4. Verifies the issue appears in the API
5. Triggers AI classification
6. Displays final statistics

**Usage:**

```bash
./scripts/send_webhook.sh
```

**Expected Output:**

```
✅ Webhook accepted
✅ Issue found in API
✅ AI classification triggered
✅ Full pipeline completed
```

**Dev JWT Details:**
- Uses `sub: '0'` with `dev_mode: true`
- Bypasses repository access filtering in Gateway
- Valid for 1 hour from generation
- Secret: `dev-jwt-secret-change-in-production-to-secure-random-key`

---

### `test-correlation-tracing.sh` - Correlation ID Tracing Test

Tests the distributed tracing system using correlation IDs across all services.

**What it tests:**
1. Sends a webhook via `send_webhook.sh`
2. Extracts the correlation ID from the response
3. Traces the correlation ID through all service logs (ingress → classifier → gateway)
4. Verifies end-to-end request tracking

**Usage:**

```bash
./scripts/test-correlation-tracing.sh
```

**Expected Output:**

```
✅ Generated Correlation ID: <uuid>
=== Tracing through services ===
1️⃣  INGRESS SERVICE: [logs with correlation_id]
2️⃣  CLASSIFIER SERVICE: [logs with correlation_id]
3️⃣  GATEWAY SERVICE: [logs with correlation_id]
✅ End-to-end tracing complete!
```

---

## Utility Scripts

### `start-prod.sh` - Production Deployment

Starts the production environment using `docker-compose.prod.yml`.

**Usage:**
```bash
./scripts/start-prod.sh
```

### `stop-prod.sh` - Production Shutdown

Stops the production environment.

**Usage:**
```bash
./scripts/stop-prod.sh
```

### `test-dev-environment.sh` - Development Environment Health Check

Tests that all development services are running and healthy.

**Usage:**
```bash
./scripts/test-dev-environment.sh
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'jose'"

Install the required dependencies:
```bash
pip install -r requirements.txt
```

### "Issue not found in API"

Check that:
1. All services are running: `docker ps`
2. Gateway service is healthy: `curl http://localhost:8002/health`
3. Classifier processed the message: `docker logs dispatchai-classifier --tail 20`
4. Issue exists in database: `docker exec dispatchai-postgres psql -U postgres -d dispatchai -c "SELECT * FROM dispatchai.issues ORDER BY created_at DESC LIMIT 1;"`

### Scripts fail with "command not found"

Make sure you're running scripts from the project root:
```bash
cd /Users/jake/code/dispatch-ai
./scripts/send_webhook.sh
```
