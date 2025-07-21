"""
DispatchAI Gateway Service
WebSocket and REST API gateway for real-time communication
"""

import os
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import asyncio
import threading

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx
from kafka import KafkaConsumer

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = FastAPI(
    title="DispatchAI Gateway Service",
    description="WebSocket and REST API gateway for real-time communication",
    version="0.1.0",
)


# Pydantic models
class IssueResponse(BaseModel):
    id: int
    number: int
    title: str
    repository: str
    category: Optional[str] = None
    priority: Optional[str] = None
    confidence: Optional[float] = None
    tags: List[str] = []
    created_at: str
    updated_at: str
    status: str = "pending"


class ClassificationUpdate(BaseModel):
    issue_id: int
    category: str
    priority: str
    confidence: float
    tags: List[str]
    similar_issues: List[Dict[str, Any]]


class ManualCorrection(BaseModel):
    issue_id: int
    category: str
    priority: str
    tags: List[str]
    notes: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    connected_clients: int


# Environment configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("Client connected", total_connections=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(
            "Client disconnected", total_connections=len(self.active_connections)
        )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        if self.active_connections:
            await asyncio.gather(
                *[
                    connection.send_text(message)
                    for connection in self.active_connections
                ],
                return_exceptions=True,
            )


manager = ConnectionManager()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="gateway",
        version="0.1.0",
        connected_clients=len(manager.active_connections),
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()

            # Echo back for now - can be extended for bidirectional communication
            await manager.send_personal_message(f"Echo: {data}", websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/issues", response_model=List[IssueResponse])
async def get_issues(
    repository: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
):
    """
    Get issues with optional filtering
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build dynamic query
            where_conditions = []
            params = []

            if repository:
                where_conditions.append("i.repository_name = %s")
                params.append(repository)

            if category:
                where_conditions.append("e.category = %s")
                params.append(category)

            if priority:
                where_conditions.append("e.priority = %s")
                params.append(priority)

            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

            query = f"""
                SELECT
                    i.id, i.issue_number, i.title, i.repository_name, i.created_at, i.updated_at,
                    e.category, e.priority, e.confidence_score, e.tags
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE {where_clause}
                ORDER BY i.created_at DESC
                LIMIT %s
            """

            params.append(limit)
            cur.execute(query, params)
            rows = cur.fetchall()

        conn.close()

        # Convert to response models
        issues = []
        for row in rows:
            issues.append(
                IssueResponse(
                    id=row["id"],
                    number=row["issue_number"],
                    title=row["title"],
                    repository=row["repository_name"],
                    category=row["category"],
                    priority=row["priority"],
                    confidence=row["confidence_score"],
                    tags=row["tags"] if isinstance(row["tags"], list) else [],
                    created_at=row["created_at"].isoformat()
                    if row["created_at"]
                    else "",
                    updated_at=row["updated_at"].isoformat()
                    if row["updated_at"]
                    else "",
                    status="classified" if row["category"] else "pending",
                )
            )

        return issues

    except Exception as e:
        logger.error("Error fetching issues", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch issues")


@app.get("/api/issues/{issue_id}", response_model=IssueResponse)
async def get_issue(issue_id: int):
    """Get a specific issue by ID"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    i.id, i.issue_number, i.title, i.body, i.repository_name, i.created_at, i.updated_at,
                    e.category, e.priority, e.confidence_score, e.tags
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE i.id = %s
            """,
                (issue_id,),
            )

            row = cur.fetchone()

        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")

        return IssueResponse(
            id=row["id"],
            number=row["issue_number"],
            title=row["title"],
            repository=row["repository_name"],
            category=row["category"],
            priority=row["priority"],
            confidence=row["confidence_score"],
            tags=row["tags"] if isinstance(row["tags"], list) else [],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
            status="classified" if row["category"] else "pending",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching issue", issue_id=issue_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch issue")


@app.post("/api/issues/{issue_id}/classify")
async def trigger_classification(issue_id: int):
    """Manually trigger classification for an issue"""
    try:
        # Get issue data
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, issue_number, title, body, labels, repository_name, repository_owner, created_at, updated_at, author
                FROM dispatchai.issues WHERE id = %s
            """,
                (issue_id,),
            )

            issue_row = cur.fetchone()

        conn.close()

        if not issue_row:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Forward to classifier service
        async with httpx.AsyncClient() as client:
            classifier_url = os.getenv(
                "CLASSIFIER_SERVICE_URL", "http://classifier:8001"
            )

            issue_data = {
                "id": issue_row["id"],
                "number": issue_row["issue_number"],
                "title": issue_row["title"],
                "body": issue_row["body"] or "",
                "labels": issue_row["labels"]
                if isinstance(issue_row["labels"], list)
                else [],
                "repository": f"{issue_row['repository_owner']}/{issue_row['repository_name']}",
                "url": f"https://github.com/{issue_row['repository_owner']}/{issue_row['repository_name']}/issues/{issue_row['issue_number']}",
                "created_at": issue_row["created_at"].isoformat(),
                "updated_at": issue_row["updated_at"].isoformat(),
                "author": issue_row["author"],
            }

            response = await client.post(
                f"{classifier_url}/classify", json=issue_data, timeout=60.0
            )
            response.raise_for_status()

            classification_result = response.json()

        # Broadcast update to connected clients
        await manager.broadcast(
            json.dumps({"type": "classification_update", "data": classification_result})
        )

        return {"status": "classification_triggered", "issue_id": issue_id}

    except httpx.RequestError as e:
        logger.error("Classifier service unavailable", error=str(e))
        raise HTTPException(status_code=503, detail="Classifier service unavailable")
    except Exception as e:
        logger.error("Error triggering classification", issue_id=issue_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to trigger classification")


@app.post("/api/test/websocket")
async def test_websocket():
    """Test endpoint to trigger WebSocket broadcast"""
    test_message = {
        "event_type": "test_message",
        "message": "WebSocket test from Gateway",
        "timestamp": datetime.now().isoformat(),
    }

    await manager.broadcast(test_message)
    return {"status": "test_message_sent", "message": test_message}


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get basic counts
            cur.execute("""
                SELECT
                    COUNT(*) as total_issues,
                    COUNT(e.issue_id) as classified_issues,
                    COUNT(*) - COUNT(e.issue_id) as pending_issues
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
            """)
            counts = cur.fetchone()

            # Get category breakdown
            cur.execute("""
                SELECT category, COUNT(*) as count
                FROM dispatchai.enriched_issues
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
            """)
            categories = cur.fetchall()

            # Get priority breakdown
            cur.execute("""
                SELECT priority, COUNT(*) as count
                FROM dispatchai.enriched_issues
                WHERE priority IS NOT NULL
                GROUP BY priority
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END
            """)
            priorities = cur.fetchall()

        conn.close()

        return {
            "total_issues": counts["total_issues"],
            "classified_issues": counts["classified_issues"],
            "pending_issues": counts["pending_issues"],
            "categories": [
                {"name": row["category"], "count": row["count"]} for row in categories
            ],
            "priorities": [
                {"name": row["priority"], "count": row["count"]} for row in priorities
            ],
            "connected_clients": len(manager.active_connections),
        }

    except Exception as e:
        logger.error("Error fetching stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@app.post("/api/issues/{issue_id}/correct")
async def apply_manual_correction(issue_id: int, correction: ManualCorrection):
    """Apply manual correction to an issue classification"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if issue exists and get enriched_issue_id
            cur.execute(
                """
                SELECT i.id, e.id as enriched_id, e.category, e.priority, e.tags
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE i.id = %s
            """,
                (issue_id,),
            )

            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Issue not found")

            enriched_id = result["enriched_id"]
            if not enriched_id:
                raise HTTPException(
                    status_code=400, detail="Issue has not been classified yet"
                )

            # Store manual corrections for changed fields
            if result["category"] != correction.category:
                cur.execute(
                    """
                    INSERT INTO dispatchai.manual_corrections (
                        enriched_issue_id, field_name, original_value, corrected_value, 
                        corrected_by, correction_reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        enriched_id,
                        "category",
                        json.dumps(result["category"]),
                        json.dumps(correction.category),
                        "user",
                        correction.notes or "Manual correction via gateway",
                    ),
                )

            if result["priority"] != correction.priority:
                cur.execute(
                    """
                    INSERT INTO dispatchai.manual_corrections (
                        enriched_issue_id, field_name, original_value, corrected_value, 
                        corrected_by, correction_reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        enriched_id,
                        "priority",
                        json.dumps(result["priority"]),
                        json.dumps(correction.priority),
                        "user",
                        correction.notes or "Manual correction via gateway",
                    ),
                )

            if result["tags"] != correction.tags:
                cur.execute(
                    """
                    INSERT INTO dispatchai.manual_corrections (
                        enriched_issue_id, field_name, original_value, corrected_value, 
                        corrected_by, correction_reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        enriched_id,
                        "tags",
                        json.dumps(result["tags"]),
                        json.dumps(correction.tags),
                        "user",
                        correction.notes or "Manual correction via gateway",
                    ),
                )

            # Update enriched_issues with manual correction
            cur.execute(
                """
                UPDATE dispatchai.enriched_issues 
                SET category = %s, priority = %s, tags = %s, updated_at = %s
                WHERE id = %s
            """,
                (
                    correction.category,
                    correction.priority,
                    correction.tags,
                    datetime.now(),
                    enriched_id,
                ),
            )

        conn.commit()
        conn.close()

        # Broadcast update to connected clients
        await manager.broadcast(
            json.dumps(
                {
                    "type": "manual_correction",
                    "data": {
                        "issue_id": issue_id,
                        "category": correction.category,
                        "priority": correction.priority,
                        "tags": correction.tags,
                        "notes": correction.notes,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
            )
        )

        logger.info(
            "Applied manual correction", issue_id=issue_id, correction=correction.dict()
        )
        return {"status": "correction_applied", "issue_id": issue_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error applying manual correction", issue_id=issue_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to apply correction")


# Serve static files for development
@app.get("/")
async def root():
    """Simple development landing page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DispatchAI Gateway</title>
    </head>
    <body>
        <h1>DispatchAI Gateway Service</h1>
        <p>WebSocket and REST API gateway is running.</p>
        <ul>
            <li><a href="/docs">API Documentation</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/api/issues">Issues API</a></li>
            <li><a href="/api/stats">Statistics</a></li>
        </ul>
        <h2>WebSocket Test</h2>
        <div id="messages"></div>
        <input type="text" id="messageText" placeholder="Type a message...">
        <button onclick="sendMessage()">Send</button>

        <script>
            const ws = new WebSocket("ws://localhost:8002/ws");

            ws.onmessage = function(event) {
                const messages = document.getElementById('messages');
                messages.innerHTML += '<div>' + event.data + '</div>';
            };

            function sendMessage() {
                const input = document.getElementById('messageText');
                ws.send(input.value);
                input.value = '';
            }

            document.getElementById('messageText').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
        </script>
    </body>
    </html>
    """)


# Kafka consumer for real-time updates
async def process_kafka_message(message):
    """Process a Kafka message and broadcast to WebSocket clients"""
    try:
        # Parse the message
        event_data = json.loads(message.value.decode("utf-8"))

        # Determine message type and format for WebSocket
        websocket_message = {
            "type": "issue_update",
            "timestamp": datetime.now().isoformat(),
            "data": event_data,
        }

        # Broadcast to all connected WebSocket clients
        await manager.broadcast(json.dumps(websocket_message))

        logger.info(
            "Broadcasted Kafka message to WebSocket clients",
            topic=message.topic,
            connected_clients=len(manager.active_connections),
        )

    except Exception as e:
        logger.error(
            "Failed to process Kafka message", error=str(e), message=str(message.value)
        )


def kafka_consumer_thread():
    """Run Kafka consumer in a separate thread"""
    try:
        print("DEBUG: Starting Kafka consumer thread...")  # Debug print
        consumer = KafkaConsumer(
            "issues.enriched",  # Listen for enriched issues
            "issues.raw",  # Also listen for raw issues
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_deserializer=lambda m: m,
            group_id="dispatchai-gateway",
            auto_offset_reset="earliest",  # Get existing messages for testing
            enable_auto_commit=True,
            consumer_timeout_ms=5000,  # Longer timeout for debugging
        )

        print("DEBUG: Consumer created, starting message loop...")  # Debug print
        logger.info(
            "Gateway Kafka consumer started", topics=["issues.enriched", "issues.raw"]
        )

        for message in consumer:
            try:
                print(f"DEBUG: Received message from {message.topic}")  # Debug print
                # Run the async processing in the event loop
                # Since we're in a thread, we need to use asyncio.run for each message
                asyncio.run(process_kafka_message(message))
            except Exception as e:
                print(f"DEBUG: Error processing message: {e}")  # Debug print
                logger.error("Error processing Kafka message in gateway", error=str(e))

    except Exception as e:
        print(f"DEBUG: Consumer thread error: {e}")  # Debug print
        logger.error("Gateway Kafka consumer error", error=str(e))


if __name__ == "__main__":
    import uvicorn

    # Start Kafka consumer in background thread
    kafka_thread = threading.Thread(target=kafka_consumer_thread, daemon=True)
    kafka_thread.start()

    uvicorn.run("app:app", host="0.0.0.0", port=8002, reload=True, log_config=None)
else:
    # When running in production (not as main), start Kafka consumer
    kafka_thread = threading.Thread(target=kafka_consumer_thread, daemon=True)
    kafka_thread.start()
