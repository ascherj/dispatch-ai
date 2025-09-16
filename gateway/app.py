"""
DispatchAI Gateway Service
WebSocket and REST API gateway for real-time communication
"""

import os
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import asyncio

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx
from kafka import KafkaConsumer
from jose import jwt, JWTError

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

# Environment configuration (moved up to be available for CORS)
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth:8003")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-production")

# CORS allowed origins (configurable for production)
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,https://localhost:3000,http://127.0.0.1:3000,http://5.78.157.202,http://5.78.157.202:3000",
).split(",")

# We'll set the lifespan after defining it below
app = FastAPI(
    title="DispatchAI Gateway Service",
    description="WebSocket and REST API gateway for real-time communication",
    version="0.1.0",
)

# Add CORS middleware to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme for JWT authentication
security = HTTPBearer(auto_error=False)


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

# Authentication helper functions
def verify_jwt_token(token: str) -> dict:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError as e:
        logger.error("JWT verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[dict]:
    """Get current user from JWT token (optional)"""
    if not credentials:
        return None
    return verify_jwt_token(credentials.credentials)

def get_current_user_required(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current user from JWT token (required)"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return verify_jwt_token(credentials.credentials)


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


# Use startup and shutdown events to manage Kafka consumer lifecycle
@app.on_event("startup")
async def startup_event():
    """Initialize Kafka consumer on startup"""
    global kafka_consumer_task
    print("DEBUG: STARTUP EVENT TRIGGERED!")  # Debug print
    logger.info("Starting DispatchAI Gateway Service")

    # Start Kafka consumer
    kafka_consumer = RobustKafkaConsumer(manager)
    kafka_consumer_task = asyncio.create_task(kafka_consumer.start())
    print("DEBUG: KAFKA CONSUMER TASK CREATED!")  # Debug print
    logger.info("Kafka consumer task started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global kafka_consumer_task
    logger.info("Shutting down DispatchAI Gateway Service")

    # Stop Kafka consumer
    if kafka_consumer_task:
        kafka_consumer_task.cancel()
        try:
            await kafka_consumer_task
        except asyncio.CancelledError:
            pass

    logger.info("Gateway service shutdown complete")


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

# Authentication and repository management endpoints (proxy to auth service)
@app.get("/auth/user/repositories")
async def get_user_repositories(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get repositories accessible by the current user (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/auth/user/repositories",
                headers={"Authorization": f"Bearer {credentials.credentials}"}  # Pass JWT token directly
            )
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    except Exception as e:
        logger.error("Error fetching repositories", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch repositories")

@app.post("/repos/{owner}/{repo}/sync")
async def sync_repository_issues(
    owner: str,
    repo: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Manually sync issues from a GitHub repository (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/repos/{owner}/{repo}/sync",
                headers={"Authorization": f"Bearer {credentials.credentials}"},  # Pass JWT token directly
                timeout=300.0  # 5 minute timeout for sync operations
            )
            response.raise_for_status()
            result = response.json()

            # Broadcast sync completion to connected clients
            await manager.broadcast(
                json.dumps({
                    "type": "sync_completed",
                    "data": {
                        "owner": owner,
                        "repo": repo,
                        "result": result,
                        "timestamp": datetime.now().isoformat(),
                    }
                })
            )

            return result

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    except Exception as e:
        logger.error("Error syncing repository", owner=owner, repo=repo, error=str(e))
        raise HTTPException(status_code=500, detail="Repository sync failed")

@app.get("/repos/{owner}/{repo}/sync-status")
async def get_sync_status(
    owner: str,
    repo: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get sync status for a repository (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/repos/{owner}/{repo}/sync-status",
                headers={"Authorization": f"Bearer {credentials.credentials}"}  # Pass JWT token directly
            )
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    except Exception as e:
        logger.error("Error fetching sync status", owner=owner, repo=repo, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch sync status")


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


# Old process_kafka_message function removed - now handled by RobustKafkaConsumer


# Global variables for consumer management
kafka_consumer_task = None
kafka_consumer_running = False


class RobustKafkaConsumer:
    """Robust Kafka consumer with reconnection and proper async integration"""

    def __init__(self, websocket_manager: ConnectionManager):
        self.manager = websocket_manager
        self.consumer = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds

    async def start(self):
        """Start the Kafka consumer with reconnection logic"""
        print("DEBUG: RobustKafkaConsumer.start() called!")  # Debug print
        self.running = True
        while self.running:
            try:
                await self._consume_messages()
            except Exception as e:
                print(f"DEBUG: Kafka consumer error: {e}")  # Debug print
                logger.error("Kafka consumer error", error=str(e))
                self.reconnect_attempts += 1

                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached, stopping consumer")
                    break

                wait_time = min(self.reconnect_delay * self.reconnect_attempts, 60)
                logger.info(
                    "Attempting to reconnect Kafka consumer",
                    attempt=self.reconnect_attempts,
                    wait_time=wait_time,
                )
                await asyncio.sleep(wait_time)

    async def _consume_messages(self):
        """Consume messages from Kafka topics"""
        try:
            # Create consumer in a thread-safe way
            consumer = await asyncio.get_event_loop().run_in_executor(
                None, self._create_consumer
            )
            self.consumer = consumer
            self.reconnect_attempts = 0  # Reset on successful connection

            print("DEBUG: Kafka consumer connected successfully!")  # Debug print
            logger.info(
                "Kafka consumer connected successfully",
                topics=["issues.enriched", "issues.raw"],
            )

            # Process messages
            while self.running:
                # Get messages in a non-blocking way
                message_batch = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: consumer.poll(timeout_ms=1000, max_records=10)
                )

                if message_batch:
                    print(
                        f"DEBUG: Received {len(message_batch)} message batches"
                    )  # Debug print
                    for topic_partition, messages in message_batch.items():
                        print(
                            f"DEBUG: Processing {len(messages)} messages from {topic_partition}"
                        )  # Debug print
                        for message in messages:
                            await self._process_message(message)
                else:
                    # Small delay when no messages to prevent busy waiting
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error("Error in Kafka message consumption", error=str(e))
            raise
        finally:
            if self.consumer:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.consumer.close
                )

    def _create_consumer(self):
        """Create Kafka consumer - runs in executor thread"""
        return KafkaConsumer(
            "issues.enriched",
            "issues.raw",
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_deserializer=lambda m: m,
            group_id="dispatchai-gateway",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            consumer_timeout_ms=1000,  # Short timeout for poll
            fetch_max_wait_ms=500,
        )

    async def _process_message(self, message):
        """Process a single Kafka message and broadcast via WebSocket"""
        try:
            print(f"DEBUG: Processing message from {message.topic}")  # Debug print

            # Parse message
            event_data = json.loads(message.value.decode("utf-8"))

            # Create WebSocket message
            websocket_message = {
                "type": "issue_update",
                "topic": message.topic,
                "timestamp": datetime.now().isoformat(),
                "data": event_data,
            }

            print(
                f"DEBUG: Broadcasting to {len(self.manager.active_connections)} WebSocket clients"
            )  # Debug print

            # Broadcast to all connected WebSocket clients
            await self.manager.broadcast(json.dumps(websocket_message))

            print(
                f"DEBUG: Successfully broadcasted message from {message.topic}"
            )  # Debug print

            logger.info(
                "Broadcasted Kafka message to WebSocket clients",
                topic=message.topic,
                connected_clients=len(self.manager.active_connections),
                message_type=websocket_message["type"],
            )

        except Exception as e:
            logger.error(
                "Error processing Kafka message",
                error=str(e),
                topic=message.topic if message else "unknown",
            )

    async def stop(self):
        """Stop the Kafka consumer gracefully"""
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.close)


if __name__ == "__main__":
    import uvicorn

    # Kafka consumer is now managed by FastAPI lifespan
    uvicorn.run("app:app", host="0.0.0.0", port=8002, reload=True, log_config=None)
else:
    # When running in production, Kafka consumer is managed by FastAPI lifespan
    pass
