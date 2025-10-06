# Kafka Issue Management & Batch Sync Cancellation Guide

## Overview

This document outlines strategies for managing issues in the Kafka pipeline, implementing safe termination of batch syncs, and controlling API costs through proper consumer management.

## Problem Statement

When syncing large repositories, the system can queue thousands of issues for classification. This creates two challenges:

1. **Cost Control**: OpenAI API costs can escalate when processing large batches
2. **Pipeline Management**: Need ability to safely cancel in-progress syncs without data inconsistency

## Architecture Components

### Data Persistence Layers

The system has three key persistence layers that must remain synchronized:

1. **Kafka Topics**
   - `issues.raw` - Raw GitHub webhook/sync events
   - `issues.enriched` - AI-classified issues
   - Default retention: 7 days
   - Messages are immutable and persist independently of consumption

2. **PostgreSQL Database**
   - `issues` - Raw issue data
   - `enriched_issues` - Classification results
   - `repository_syncs` - Sync operation tracking
   - Source of truth for application state

3. **Consumer Offsets**
   - Tracks where Classifier and Gateway services left off
   - Managed by Kafka consumer groups
   - Can be manipulated for replay/skip scenarios

### Message Flow

```
GitHub API/Webhook → Ingress → Kafka (issues.raw) → Classifier → Postgres + Kafka (issues.enriched) → Gateway → WebSocket
```

## Recommended Solutions

### 1. Consumer Management for Safe Termination

**Current Issue**: Classifier service uses auto-commit which can cause message reprocessing on abrupt shutdown.

**Location**: `classifier/app.py:655`

**Change**:
```python
# Before
enable_auto_commit=True,

# After
enable_auto_commit=False,  # Manual offset control
```

**New Control Endpoints** (add to `classifier/app.py`):

```python
# Global flag for pausing processing
kafka_consumer_running = True

@app.post("/admin/pause-processing")
async def pause_kafka_processing():
    """Pause Kafka message processing (for cost control)"""
    global kafka_consumer_running
    kafka_consumer_running = False
    logger.info("Kafka processing paused by admin")
    return {"status": "paused", "message": "Processing will pause after current message"}

@app.post("/admin/resume-processing")
async def resume_kafka_processing():
    """Resume Kafka message processing"""
    global kafka_consumer_running
    kafka_consumer_running = True
    logger.info("Kafka processing resumed by admin")
    return {"status": "resumed"}

@app.get("/admin/processing-status")
async def get_processing_status():
    """Get current processing status and queue depth"""
    try:
        # Check consumer lag
        admin_client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","))
        consumer_group_offsets = admin_client.list_consumer_group_offsets("dispatchai-classifier")
        
        return {
            "processing_enabled": kafka_consumer_running,
            "consumer_group": "dispatchai-classifier",
            "offsets": consumer_group_offsets
        }
    except Exception as e:
        logger.error("Failed to get processing status", error=str(e))
        return {"processing_enabled": kafka_consumer_running, "error": str(e)}
```

**Update consumer loop** (modify `kafka_consumer_thread` function):

```python
def kafka_consumer_thread():
    """Run Kafka consumer in a separate thread"""
    try:
        consumer = KafkaConsumer(
            "issues.raw",
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_deserializer=lambda m: m,
            group_id="dispatchai-classifier",
            auto_offset_reset="earliest",
            enable_auto_commit=False,  # Changed
        )

        logger.info("Kafka consumer started", topic="issues.raw")

        for message in consumer:
            # Check if processing is paused
            if not kafka_consumer_running:
                logger.info("Processing paused, skipping message")
                time.sleep(1)
                continue
                
            try:
                # Run the async processing in the event loop
                asyncio.run(process_kafka_message(message))
                
                # Manually commit offset after successful processing
                consumer.commit()
                
            except Exception as e:
                logger.error("Error processing Kafka message", error=str(e))
                # Don't commit offset - message will be reprocessed

    except Exception as e:
        logger.error("Kafka consumer error", error=str(e))
```

### 2. Batch Sync Cancellation Endpoint

**Add to `gateway/app.py`**:

```python
class CancelSyncResponse(BaseModel):
    success: bool
    message: str
    issues_removed: int
    issues_classified: int

@app.delete("/repos/{owner}/{repo}/sync", response_model=CancelSyncResponse)
async def cancel_repository_sync(
    owner: str, 
    repo: str, 
    current_user: dict = Depends(get_current_user_required)
):
    """
    Cancel ongoing repository sync and clean up unprocessed issues
    
    This endpoint:
    1. Marks the sync as cancelled in repository_syncs table
    2. Deletes unprocessed issues from the database
    3. Keeps classified issues (work already done)
    4. Kafka messages remain but become orphaned (no DB records)
    """
    try:
        user_id = current_user["sub"]
        
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if sync exists and is in progress
            cur.execute("""
                SELECT sync_status, issues_synced
                FROM dispatchai.repository_syncs
                WHERE user_id = %s 
                AND repository_owner = %s 
                AND repository_name = %s
            """, (user_id, owner, repo))
            
            sync_record = cur.fetchone()
            if not sync_record:
                raise HTTPException(status_code=404, detail="No sync found for this repository")
            
            if sync_record["sync_status"] not in ["syncing", "pending"]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot cancel sync in status: {sync_record['sync_status']}"
                )
            
            # Count issues before deletion
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE e.id IS NULL) as unprocessed,
                    COUNT(*) FILTER (WHERE e.id IS NOT NULL) as processed
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE i.repository_owner = %s 
                AND i.repository_name = %s
                AND i.pulled_by_user_id = %s
                AND i.sync_source = 'manual_pull'
            """, (owner, repo, user_id))
            
            counts = cur.fetchone()
            unprocessed = counts["unprocessed"] or 0
            processed = counts["processed"] or 0
            
            # Update sync status to cancelled
            cur.execute("""
                UPDATE dispatchai.repository_syncs
                SET sync_status = 'cancelled', 
                    error_message = 'Cancelled by user',
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s 
                AND repository_owner = %s 
                AND repository_name = %s
            """, (user_id, owner, repo))
            
            # Delete unprocessed issues (not yet classified)
            cur.execute("""
                DELETE FROM dispatchai.issues i
                WHERE i.repository_owner = %s 
                AND i.repository_name = %s
                AND i.pulled_by_user_id = %s
                AND i.sync_source = 'manual_pull'
                AND NOT EXISTS (
                    SELECT 1 FROM dispatchai.enriched_issues e 
                    WHERE e.issue_id = i.id
                )
            """, (owner, repo, user_id))
            
            deleted_count = cur.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(
            "Sync cancelled",
            user_id=user_id,
            owner=owner,
            repo=repo,
            deleted=deleted_count,
            kept_classified=processed
        )
        
        # Broadcast cancellation to connected clients
        await manager.broadcast(
            json.dumps({
                "type": "sync_cancelled",
                "data": {
                    "owner": owner,
                    "repo": repo,
                    "issues_removed": deleted_count,
                    "issues_kept": processed,
                    "timestamp": datetime.now().isoformat(),
                }
            })
        )
        
        return CancelSyncResponse(
            success=True,
            message=f"Sync cancelled. Removed {deleted_count} unprocessed issues, kept {processed} classified issues.",
            issues_removed=deleted_count,
            issues_classified=processed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error cancelling sync", owner=owner, repo=repo, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to cancel sync")
```

### 3. Kafka Configuration by Environment

**Development** (`docker-compose.yml`):

```yaml
redpanda:
  environment:
    # Short retention for development (1 hour)
    - REDPANDA_KAFKA_LOG_RETENTION_MS=3600000
    # Small segments for easier cleanup
    - REDPANDA_KAFKA_LOG_SEGMENT_MS=600000
```

**Production** (`docker-compose.prod.yml`):

```yaml
redpanda:
  environment:
    # Longer retention for audit trails (7 days)
    - REDPANDA_KAFKA_LOG_RETENTION_MS=604800000
    # Larger segments for efficiency
    - REDPANDA_KAFKA_LOG_SEGMENT_MS=86400000
```

### 4. Consumer Offset Management Commands

**Skip to end of queue** (ignore backlog):
```bash
# Skip all unprocessed messages
docker exec dispatchai-redpanda rpk group seek dispatchai-classifier --to end
```

**Replay from beginning**:
```bash
# Reprocess all messages in retention window
docker exec dispatchai-redpanda rpk group seek dispatchai-classifier --to start
```

**Check consumer lag**:
```bash
# See how many messages are queued
docker exec dispatchai-redpanda rpk group describe dispatchai-classifier
```

**Reset specific partition**:
```bash
# Reset partition 0 to offset 100
docker exec dispatchai-redpanda rpk group seek dispatchai-classifier \
  --to start --partitions 0:100
```

### 5. Idempotent Processing Enhancement

**Add duplicate check before classification** (`classifier/app.py`):

```python
async def store_enriched_issue(
    issue: IssueData,
    classification: Dict[str, Any],
    similar_issues: List[Dict[str, Any]],
    embedding: Optional[List[float]] = None,
):
    """Store enriched issue with classification results"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            # Get internal issue ID
            cur.execute("""
                SELECT id FROM dispatchai.issues
                WHERE github_issue_id = %s
            """, (issue.id,))
            
            result = cur.fetchone()
            if not result:
                logger.error("Issue not found in database", github_issue_id=issue.id)
                return
            
            internal_issue_id = result[0]
            
            # Check if already enriched (idempotency)
            cur.execute("""
                SELECT id FROM dispatchai.enriched_issues 
                WHERE issue_id = %s
            """, (internal_issue_id,))
            
            if cur.fetchone():
                logger.info(
                    "Issue already enriched, skipping duplicate classification",
                    issue_id=issue.id,
                    internal_id=internal_issue_id
                )
                return
            
            # Store enriched data (rest of existing logic)
            cur.execute("""
                INSERT INTO dispatchai.enriched_issues (...)
                VALUES (...)
            """, (...))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to store enriched issue", issue_id=issue.id, error=str(e))
```

### 6. Cost Management Strategies

#### Option A: Rate Limiting

```python
# Add to classifier/app.py
import asyncio
from datetime import datetime, timedelta

RATE_LIMIT_PER_MINUTE = int(os.getenv("CLASSIFY_RATE_LIMIT", "10"))
classification_semaphore = asyncio.Semaphore(RATE_LIMIT_PER_MINUTE)
classification_count = 0
classification_window_start = datetime.now()

async def classify_issue(issue: IssueData):
    global classification_count, classification_window_start
    
    # Reset counter every minute
    if datetime.now() - classification_window_start > timedelta(minutes=1):
        classification_count = 0
        classification_window_start = datetime.now()
    
    # Check rate limit
    if classification_count >= RATE_LIMIT_PER_MINUTE:
        wait_time = 60 - (datetime.now() - classification_window_start).seconds
        logger.warning(f"Rate limit reached, waiting {wait_time}s")
        await asyncio.sleep(wait_time)
        classification_count = 0
        classification_window_start = datetime.now()
    
    async with classification_semaphore:
        classification_count += 1
        # Existing classification logic
        ...
```

#### Option B: Daily Budget Control

```python
# Add to classifier/app.py
DAILY_BUDGET_LIMIT = int(os.getenv("DAILY_CLASSIFICATION_LIMIT", "1000"))

@app.get("/admin/budget-status")
async def get_budget_status():
    """Get today's classification budget status"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM dispatchai.enriched_issues
                WHERE DATE(processed_at) = CURRENT_DATE
            """)
            result = cur.fetchone()
            today_count = result[0] if result else 0
        conn.close()
        
        remaining = max(0, DAILY_BUDGET_LIMIT - today_count)
        
        return {
            "daily_limit": DAILY_BUDGET_LIMIT,
            "used_today": today_count,
            "remaining": remaining,
            "percentage_used": (today_count / DAILY_BUDGET_LIMIT * 100) if DAILY_BUDGET_LIMIT > 0 else 0
        }
    except Exception as e:
        logger.error("Failed to get budget status", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get budget status")

async def classify_issue(issue: IssueData):
    # Check daily budget before classification
    budget_status = await get_budget_status()
    if budget_status["remaining"] <= 0:
        logger.warning("Daily classification budget exhausted")
        raise HTTPException(
            status_code=429, 
            detail=f"Daily classification budget of {DAILY_BUDGET_LIMIT} reached"
        )
    
    # Existing classification logic
    ...
```

#### Option C: Large Sync Confirmation

```python
# Add to auth service (where sync is initiated)
LARGE_SYNC_THRESHOLD = int(os.getenv("LARGE_SYNC_THRESHOLD", "100"))
ESTIMATED_COST_PER_ISSUE = float(os.getenv("COST_PER_ISSUE", "0.01"))

@app.post("/repos/{owner}/{repo}/sync")
async def sync_repository_issues(owner: str, repo: str, force: bool = False):
    # Get issue count from GitHub
    issue_count = await get_github_issue_count(owner, repo)
    
    if issue_count > LARGE_SYNC_THRESHOLD and not force:
        estimated_cost = issue_count * ESTIMATED_COST_PER_ISSUE
        return {
            "requires_confirmation": True,
            "issue_count": issue_count,
            "estimated_cost_usd": round(estimated_cost, 2),
            "message": f"This repository has {issue_count} issues. Use ?force=true to proceed."
        }
    
    # Proceed with sync
    ...
```

## Operational Procedures

### Cancel an In-Progress Sync

```bash
# Via API
curl -X DELETE "http://localhost:8002/repos/owner/repo/sync" \
  -H "Authorization: Bearer $TOKEN"
```

### Pause All Classification Processing

```bash
# Pause processing
curl -X POST "http://localhost:8001/admin/pause-processing"

# Check status
curl "http://localhost:8001/admin/processing-status"

# Resume processing
curl -X POST "http://localhost:8001/admin/resume-processing"
```

### Skip Unprocessed Messages

```bash
# Skip to end of queue (ignore backlog)
docker exec dispatchai-redpanda rpk group seek dispatchai-classifier --to end

# Check remaining lag
docker exec dispatchai-redpanda rpk group describe dispatchai-classifier
```

### Monitor Classification Budget

```bash
# Check today's usage
curl "http://localhost:8001/admin/budget-status"
```

## Key Principles

1. **Kafka is Event Log, Postgres is Truth**
   - Kafka messages are delivery mechanism
   - Postgres database is source of truth
   - Deleting Postgres records is sufficient for cancellation

2. **Idempotency is Critical**
   - All operations must handle duplicate messages safely
   - Check for existing records before processing
   - Use ON CONFLICT clauses in SQL

3. **Manual Offset Management**
   - Disable auto-commit for precise control
   - Commit offsets only after successful processing
   - Allow manual seek operations for backlog management

4. **Cost Control Through Throttling**
   - Implement rate limiting at classifier level
   - Track daily budgets
   - Require confirmation for large syncs
   - Provide pause/resume controls

5. **Clean Cancellation**
   - Mark sync as cancelled in tracking table
   - Delete unprocessed issues from database
   - Keep classified issues (work already done)
   - Kafka messages age out based on retention policy

## Implementation Checklist

- [ ] Update Classifier to use manual offset commits
- [ ] Add pause/resume endpoints to Classifier
- [ ] Add sync cancellation endpoint to Gateway
- [ ] Implement idempotent processing checks
- [ ] Configure environment-specific Kafka retention
- [ ] Add budget tracking endpoints
- [ ] Implement rate limiting for classifications
- [ ] Add large sync confirmation logic
- [ ] Document operational procedures
- [ ] Test cancellation workflow end-to-end

## Testing Scenarios

1. **Cancel Mid-Sync**: Start sync, cancel after partial processing, verify unprocessed issues removed
2. **Pause/Resume**: Pause processing, verify messages queue up, resume and verify processing continues
3. **Skip Queue**: Build up backlog, skip to end, verify old messages ignored
4. **Budget Limit**: Reach daily limit, verify new classifications rejected
5. **Idempotency**: Process same message twice, verify no duplicates created

## Future Enhancements

1. **Dead Letter Queue**: Move failed messages to separate topic for analysis
2. **Selective Replay**: Replay specific date ranges or issue numbers
3. **Multi-tenant Budgets**: Per-user classification limits
4. **Cost Analytics**: Track actual API costs vs. estimates
5. **Smart Batching**: Group similar issues for more efficient processing
