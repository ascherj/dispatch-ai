"""
DispatchAI Gateway Service
WebSocket and REST API gateway for real-time communication
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

import structlog
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Depends,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx
from kafka import KafkaConsumer
from jose import jwt, JWTError
from github_client import GitHubAPIClient, validate_public_repository, parse_github_url

# Configure structured logging
import logging

# Set up Python's standard logging to respect LOG_LEVEL
logging.basicConfig(
    format="%(message)s",
    level=os.getenv("LOG_LEVEL", "INFO"),
)

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


# Metrics tracking
class ServiceMetrics:
    """In-memory metrics tracking for observability"""
    def __init__(self):
        self.start_time = datetime.now()
        self.messages_broadcast = 0
        self.api_requests = 0
        self.api_latencies_ms = []
        
    def record_message_broadcast(self):
        self.messages_broadcast += 1
    
    def record_api_request(self):
        self.api_requests += 1
    
    def record_api_latency(self, latency_ms: float):
        self.api_latencies_ms.append(latency_ms)
        # Keep only last 1000 measurements
        if len(self.api_latencies_ms) > 1000:
            self.api_latencies_ms = self.api_latencies_ms[-1000:]
    
    def get_percentile(self, percentile: int) -> float:
        """Calculate percentile from API latencies"""
        if not self.api_latencies_ms:
            return 0.0
        sorted_times = sorted(self.api_latencies_ms)
        index = int(len(sorted_times) * percentile / 100)
        return round(sorted_times[min(index, len(sorted_times) - 1)], 2)
    
    def get_uptime_seconds(self) -> int:
        return int((datetime.now() - self.start_time).total_seconds())
    
    def to_dict(self, active_connections: int) -> Dict[str, Any]:
        return {
            "service": "gateway",
            "websocket_connections_active": active_connections,
            "messages_broadcast": self.messages_broadcast,
            "api_requests": self.api_requests,
            "api_latency_ms": {
                "p50": self.get_percentile(50),
                "p95": self.get_percentile(95),
                "p99": self.get_percentile(99),
            },
            "uptime_seconds": self.get_uptime_seconds(),
        }

metrics = ServiceMetrics()


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


class RepositoryResponse(BaseModel):
    owner: str
    name: str
    full_name: str
    permissions: Dict[str, bool]
    connected: bool = False
    last_sync_at: Optional[str] = None
    issues_synced: int = 0
    sync_status: Optional[str] = None


class ConnectRepositoryRequest(BaseModel):
    owner: str
    name: str
    is_public: bool = True


class ConnectRepositoryResponse(BaseModel):
    success: bool
    message: str
    repository: Optional[RepositoryResponse] = None


class PublicRepositoryRequest(BaseModel):
    github_url: str


class DisconnectRepositoryResponse(BaseModel):
    success: bool
    message: str


class OrganizationResponse(BaseModel):
    id: int
    login: str
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: str
    html_url: str
    type: str  # "Organization" or "User"
    public_repos: int
    total_private_repos: Optional[int] = None
    accessible_repos: Optional[int] = None


class OrganizationRepositoriesResponse(BaseModel):
    organization: str
    repositories: List[RepositoryResponse]


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
            detail="Invalid authentication token",
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Get current user from JWT token (optional)"""
    if not credentials:
        return None
    return verify_jwt_token(credentials.credentials)


def get_current_user_required(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Get current user from JWT token (required)"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return verify_jwt_token(credentials.credentials)


async def get_user_github_token(user_id: int) -> str:
    """Get GitHub access token for user from auth service"""
    try:
        async with httpx.AsyncClient() as client:
            # This endpoint would need to be created in auth service
            response = await client.get(
                f"{AUTH_SERVICE_URL}/auth/user/{user_id}/github-token", timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
    except Exception as e:
        logger.error("Failed to get user GitHub token", user_id=user_id, error=str(e))
        raise HTTPException(status_code=401, detail="GitHub token not available")


# WebSocket connection manager with user context
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, Optional[dict]] = {}

    async def connect(self, websocket: WebSocket, user: Optional[dict] = None):
        await websocket.accept()
        self.active_connections[websocket] = user
        logger.info(
            "Client connected",
            total_connections=len(self.active_connections),
            authenticated=user is not None,
            user_id=user.get("sub") if user else None,
        )

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)
        logger.info(
            "Client disconnected", total_connections=len(self.active_connections)
        )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, user_filter: Optional[callable] = None):
        if self.active_connections:
            tasks = []
            for connection, user in self.active_connections.items():
                if user_filter is None or user_filter(user):
                    tasks.append(connection.send_text(message))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


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


@app.get("/metrics")
async def get_metrics():
    """Expose operational metrics for monitoring"""
    return metrics.to_dict(active_connections=len(manager.active_connections))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket endpoint for real-time updates with JWT authentication"""
    user = None

    if token:
        try:
            user = verify_jwt_token(token)
            logger.info("WebSocket connection authenticated", user_id=user.get("sub"))
        except HTTPException:
            logger.warning("WebSocket connection with invalid token")
            await websocket.close(code=1008, reason="Invalid authentication token")
            return
    else:
        logger.info("WebSocket connection without authentication (public access)")

    await manager.connect(websocket, user)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Echo: {data}", websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/public/repos/{owner}/{repo}/issues", response_model=List[IssueResponse])
async def get_public_repository_issues(
    owner: str,
    repo: str,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
):
    """Get issues from a public repository (no auth required)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT is_public_dashboard FROM dispatchai.repositories
                WHERE owner = %s AND name = %s
                """,
                (owner, repo),
            )
            repo_row = cur.fetchone()

            if not repo_row or not repo_row["is_public_dashboard"]:
                raise HTTPException(
                    status_code=404, detail="Public repository not found"
                )

            where_conditions = ["i.repository_owner = %s", "i.repository_name = %s"]
            params = [owner, repo]

            if category:
                where_conditions.append("e.category = %s")
                params.append(category)

            if priority:
                where_conditions.append("e.priority = %s")
                params.append(priority)

            where_clause = " AND ".join(where_conditions)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching public repository issues",
            owner=owner,
            repo=repo,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to fetch issues")


@app.get("/api/issues", response_model=List[IssueResponse])
async def get_issues(
    repository: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user_required),
):
    """
    Get issues with optional filtering for authenticated user only
    """
    try:
        user_id = current_user["sub"]
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build dynamic query - only show issues from user's connected repositories or issues pulled by the user
            where_conditions = [
                """(
                    EXISTS (
                        SELECT 1 FROM dispatchai.user_repositories ur
                        JOIN dispatchai.repositories r ON ur.repo_id = r.id
                        WHERE ur.user_id = %s
                        AND r.owner = i.repository_owner
                        AND r.name = i.repository_name
                    )
                    OR i.pulled_by_user_id = %s
                )"""
            ]
            params = [user_id, user_id]

            if repository:
                where_conditions.append("i.repository_name = %s")
                params.append(repository)

            if category:
                where_conditions.append("e.category = %s")
                params.append(category)

            if priority:
                where_conditions.append("e.priority = %s")
                params.append(priority)

            where_clause = " AND ".join(where_conditions)

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
async def get_issue(
    issue_id: int, current_user: Optional[dict] = Depends(get_current_user)
):
    """Get a specific issue by ID (requires auth or public repo)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    i.id, i.issue_number, i.title, i.body, i.repository_name, i.repository_owner, i.created_at, i.updated_at,
                    e.category, e.priority, e.confidence_score, e.tags,
                    r.is_public_dashboard
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                LEFT JOIN dispatchai.repositories r ON r.owner = i.repository_owner AND r.name = i.repository_name
                WHERE i.id = %s
            """,
                (issue_id,),
            )

            row = cur.fetchone()

        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")

        is_public = row.get("is_public_dashboard", False)
        if not is_public and not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not is_public and current_user:
            user_id = current_user.get("sub")
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM dispatchai.user_repositories ur
                    JOIN dispatchai.repositories r ON ur.repo_id = r.id
                    WHERE ur.user_id = %s
                    AND r.owner = %s
                    AND r.name = %s
                    """,
                    (user_id, row["repository_owner"], row["repository_name"]),
                )
                has_access = cur.fetchone() is not None
            conn.close()

            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied")

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


@app.get("/api/public/repos/{owner}/{repo}/stats")
async def get_public_repository_stats(owner: str, repo: str):
    """Get statistics for a public repository (no auth required)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT is_public_dashboard FROM dispatchai.repositories
                WHERE owner = %s AND name = %s
                """,
                (owner, repo),
            )
            repo_row = cur.fetchone()

            if not repo_row or not repo_row["is_public_dashboard"]:
                raise HTTPException(
                    status_code=404, detail="Public repository not found"
                )

            cur.execute(
                """
                SELECT
                    COUNT(*) as total_issues,
                    COUNT(e.issue_id) as classified_issues,
                    COUNT(*) - COUNT(e.issue_id) as pending_issues
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE i.repository_owner = %s AND i.repository_name = %s
            """,
                (owner, repo),
            )
            counts = cur.fetchone()

            cur.execute(
                """
                SELECT category, COUNT(*) as count
                FROM dispatchai.enriched_issues e
                JOIN dispatchai.issues i ON e.issue_id = i.id
                WHERE category IS NOT NULL
                AND i.repository_owner = %s AND i.repository_name = %s
                GROUP BY category
                ORDER BY count DESC
            """,
                (owner, repo),
            )
            categories = cur.fetchall()

            cur.execute(
                """
                SELECT priority, COUNT(*) as count
                FROM dispatchai.enriched_issues e
                JOIN dispatchai.issues i ON e.issue_id = i.id
                WHERE priority IS NOT NULL
                AND i.repository_owner = %s AND i.repository_name = %s
                GROUP BY priority
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END
            """,
                (owner, repo),
            )
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
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching public repository stats",
            owner=owner,
            repo=repo,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@app.get("/api/stats")
async def get_stats(current_user: dict = Depends(get_current_user_required)):
    """Get dashboard statistics for authenticated user only"""
    try:
        user_id = current_user["sub"]
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get basic counts - only for user's accessible repositories
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_issues,
                    COUNT(e.issue_id) as classified_issues,
                    COUNT(*) - COUNT(e.issue_id) as pending_issues
                FROM dispatchai.issues i
                LEFT JOIN dispatchai.enriched_issues e ON i.id = e.issue_id
                WHERE (
                    EXISTS (
                        SELECT 1 FROM dispatchai.user_repositories ur
                        JOIN dispatchai.repositories r ON ur.repo_id = r.id
                        WHERE ur.user_id = %s
                        AND r.owner = i.repository_owner
                        AND r.name = i.repository_name
                    )
                    OR i.pulled_by_user_id = %s
                )
            """,
                (user_id, user_id),
            )
            counts = cur.fetchone()

            # Get category breakdown - only for user's accessible repositories
            cur.execute(
                """
                SELECT category, COUNT(*) as count
                FROM dispatchai.enriched_issues e
                JOIN dispatchai.issues i ON e.issue_id = i.id
                WHERE category IS NOT NULL
                AND (
                    EXISTS (
                        SELECT 1 FROM dispatchai.user_repositories ur
                        JOIN dispatchai.repositories r ON ur.repo_id = r.id
                        WHERE ur.user_id = %s
                        AND r.owner = i.repository_owner
                        AND r.name = i.repository_name
                    )
                    OR i.pulled_by_user_id = %s
                )
                GROUP BY category
                ORDER BY count DESC
            """,
                (user_id, user_id),
            )
            categories = cur.fetchall()

            # Get priority breakdown - only for user's accessible repositories
            cur.execute(
                """
                SELECT priority, COUNT(*) as count
                FROM dispatchai.enriched_issues e
                JOIN dispatchai.issues i ON e.issue_id = i.id
                WHERE priority IS NOT NULL
                AND (
                    EXISTS (
                        SELECT 1 FROM dispatchai.user_repositories ur
                        JOIN dispatchai.repositories r ON ur.repo_id = r.id
                        WHERE ur.user_id = %s
                        AND r.owner = i.repository_owner
                        AND r.name = i.repository_name
                    )
                    OR i.pulled_by_user_id = %s
                )
                GROUP BY priority
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END
            """,
                (user_id, user_id),
            )
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
async def get_user_repositories(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get repositories accessible by the current user (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/auth/user/repositories",
                headers={
                    "Authorization": f"Bearer {credentials.credentials}"
                },  # Pass JWT token directly
            )
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        )
    except Exception as e:
        logger.error("Error fetching repositories", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch repositories")


@app.post("/repos/{owner}/{repo}/sync")
async def sync_repository_issues(
    owner: str, repo: str, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Manually sync issues from a GitHub repository (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/repos/{owner}/{repo}/sync",
                headers={
                    "Authorization": f"Bearer {credentials.credentials}"
                },  # Pass JWT token directly
                timeout=300.0,  # 5 minute timeout for sync operations
            )
            response.raise_for_status()
            result = response.json()

            # Broadcast sync completion to connected clients
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "sync_completed",
                        "data": {
                            "owner": owner,
                            "repo": repo,
                            "result": result,
                            "timestamp": datetime.now().isoformat(),
                        },
                    }
                )
            )

            return result

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        )
    except Exception as e:
        logger.error("Error syncing repository", owner=owner, repo=repo, error=str(e))
        raise HTTPException(status_code=500, detail="Repository sync failed")


@app.get("/repos/{owner}/{repo}/sync-status")
async def get_sync_status(
    owner: str, repo: str, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get sync status for a repository (proxy to auth service)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/repos/{owner}/{repo}/sync-status",
                headers={
                    "Authorization": f"Bearer {credentials.credentials}"
                },  # Pass JWT token directly
            )
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error("Auth service request failed", error=str(e))
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable"
        )
    except Exception as e:
        logger.error("Error fetching sync status", owner=owner, repo=repo, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch sync status")


# Repository Management Endpoints (moved from auth service)


@app.post("/api/repos/connect", response_model=ConnectRepositoryResponse)
async def connect_repository(
    request: ConnectRepositoryRequest,
    current_user: dict = Depends(get_current_user_required),
):
    """Connect a repository to the user's account"""
    try:
        user_id = current_user["sub"]

        # Get user's GitHub access token from auth service
        github_token = await get_user_github_token(user_id)

        # Verify repository access and get metadata
        async with GitHubAPIClient(github_token) as github_client:
            try:
                repo_info = await github_client.get_repository_info(
                    request.owner, request.name
                )
            except Exception as e:
                if "404" in str(e):
                    raise HTTPException(
                        status_code=404, detail="Repository not found or no access"
                    )
                elif "403" in str(e):
                    raise HTTPException(
                        status_code=403, detail="Insufficient permissions"
                    )
                else:
                    raise HTTPException(
                        status_code=500, detail="Failed to verify repository access"
                    )

        # Check for deduplication - repository already exists
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM dispatchai.repositories
                WHERE github_repo_id = %s OR (owner = %s AND name = %s)
            """,
                (repo_info["id"], request.owner, request.name),
            )
            existing_repo = cur.fetchone()

            if existing_repo:
                repo_id = existing_repo[0]
                # Check if user is already connected
                cur.execute(
                    """
                    SELECT 1 FROM dispatchai.user_repositories
                    WHERE user_id = %s AND repo_id = %s
                """,
                    (user_id, repo_id),
                )
                if cur.fetchone():
                    conn.close()
                    return ConnectRepositoryResponse(
                        success=False,
                        message="Repository already connected to your account",
                    )
            else:
                # Create new repository record
                cur.execute(
                    """
                    INSERT INTO dispatchai.repositories (
                        github_repo_id, owner, name, private, is_public_dashboard
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        repo_info["id"],
                        request.owner,
                        request.name,
                        repo_info["private"],
                        not repo_info["private"] and request.is_public,
                    ),
                )
                repo_id = cur.fetchone()[0]

            # Connect user to repository
            cur.execute(
                """
                INSERT INTO dispatchai.user_repositories (user_id, repo_id, role, can_write)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, repo_id) DO NOTHING
            """,
                (
                    user_id,
                    repo_id,
                    "owner" if repo_info["permissions"]["admin"] else "viewer",
                    repo_info["permissions"]["push"],
                ),
            )

        conn.commit()
        conn.close()

        logger.info(
            "Repository connected",
            user_id=user_id,
            owner=request.owner,
            repo=request.name,
        )

        return ConnectRepositoryResponse(
            success=True,
            message="Repository connected successfully",
            repository=RepositoryResponse(
                owner=request.owner,
                name=request.name,
                full_name=f"{request.owner}/{request.name}",
                permissions={
                    "admin": repo_info["permissions"]["admin"],
                    "push": repo_info["permissions"]["push"],
                    "pull": repo_info["permissions"]["pull"],
                },
                connected=True,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error connecting repository", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to connect repository")


@app.post("/api/repos/validate-public", response_model=ConnectRepositoryResponse)
async def validate_public_repository_endpoint(request: PublicRepositoryRequest):
    """Validate and get metadata for a public GitHub repository URL"""
    try:
        owner, repo = parse_github_url(request.github_url)
        await validate_public_repository(request.github_url)

        return ConnectRepositoryResponse(
            success=True,
            message="Public repository validated",
            repository=RepositoryResponse(
                owner=owner,
                name=repo,
                full_name=f"{owner}/{repo}",
                permissions={"admin": False, "push": False, "pull": True},
                connected=False,
            ),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Error validating public repository", url=request.github_url, error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to validate repository")


@app.delete("/api/repos/{owner}/{repo}", response_model=DisconnectRepositoryResponse)
async def disconnect_repository(
    owner: str, repo: str, current_user: dict = Depends(get_current_user_required)
):
    """Disconnect a repository from the user's account"""
    try:
        user_id = current_user["sub"]

        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            # Find repository
            cur.execute(
                """
                SELECT r.id FROM dispatchai.repositories r
                WHERE r.owner = %s AND r.name = %s
            """,
                (owner, repo),
            )
            repo_record = cur.fetchone()

            if not repo_record:
                conn.close()
                raise HTTPException(status_code=404, detail="Repository not found")

            repo_id = repo_record[0]

            # Check if user is connected
            cur.execute(
                """
                SELECT 1 FROM dispatchai.user_repositories
                WHERE user_id = %s AND repo_id = %s
            """,
                (user_id, repo_id),
            )

            if not cur.fetchone():
                conn.close()
                return DisconnectRepositoryResponse(
                    success=False, message="Repository not connected to your account"
                )

            # Remove user-repository connection
            cur.execute(
                """
                DELETE FROM dispatchai.user_repositories
                WHERE user_id = %s AND repo_id = %s
            """,
                (user_id, repo_id),
            )

            # Also remove sync records for this user
            cur.execute(
                """
                DELETE FROM dispatchai.repository_syncs
                WHERE user_id = %s AND repository_owner = %s AND repository_name = %s
            """,
                (user_id, owner, repo),
            )

        conn.commit()
        conn.close()

        logger.info("Repository disconnected", user_id=user_id, owner=owner, repo=repo)

        return DisconnectRepositoryResponse(
            success=True, message="Repository disconnected successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error disconnecting repository", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to disconnect repository")


# Organization and Repository Management Endpoints


@app.get("/api/organizations", response_model=List[OrganizationResponse])
async def get_user_organizations(
    current_user: dict = Depends(get_current_user_required),
):
    """Get organizations and user account that the authenticated user has repository access to"""
    try:
        user_id = current_user["sub"]

        # Get user's GitHub access token
        github_token = await get_user_github_token(user_id)
        if not github_token:
            raise HTTPException(status_code=401, detail="GitHub token not found")

        # Fetch organizations using GitHub API client
        async with GitHubAPIClient(github_token) as github_client:
            organizations = await github_client.get_user_organizations()

            # Fetch accessible repos count for each organization
            result = []
            for org in organizations:
                # Get accessible repositories for this org to get accurate count
                # Limit to 200 repos for performance (just for counting)
                accessible_repos = await github_client.get_organization_repositories(
                    org.login, max_repos=200
                )

                result.append(
                    OrganizationResponse(
                        id=org.id,
                        login=org.login,
                        name=org.name,
                        description=org.description,
                        avatar_url=org.avatar_url,
                        html_url=org.html_url,
                        type=org.type,
                        public_repos=org.public_repos,
                        total_private_repos=org.total_private_repos,
                        accessible_repos=len(accessible_repos),
                    )
                )

        logger.info("Fetched user organizations", user_id=user_id, count=len(result))
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching organizations",
            user_id=current_user.get("sub"),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to fetch organizations")


@app.get(
    "/api/organizations/{org_login}/repositories",
    response_model=OrganizationRepositoriesResponse,
)
async def get_organization_repositories(
    org_login: str, current_user: dict = Depends(get_current_user_required)
):
    """Get repositories for a specific organization or user"""
    try:
        user_id = current_user["sub"]

        # Get user's GitHub access token
        github_token = await get_user_github_token(user_id)
        if not github_token:
            raise HTTPException(status_code=401, detail="GitHub token not found")

        # Fetch organization repositories using GitHub API client
        async with GitHubAPIClient(github_token) as github_client:
            repositories = await github_client.get_organization_repositories(org_login)

        # Get sync status and connection status from database
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            # Get sync status
            cur.execute(
                """
                SELECT repository_owner, repository_name, last_sync_at, issues_synced, sync_status
                FROM dispatchai.repository_syncs
                WHERE user_id = %s
            """,
                (user_id,),
            )
            sync_data = {
                f"{row[0]}/{row[1]}": {
                    "last_sync_at": row[2].isoformat() if row[2] else None,
                    "issues_synced": row[3],
                    "sync_status": row[4],
                }
                for row in cur.fetchall()
            }

            # Get connection status
            cur.execute(
                """
                SELECT r.owner, r.name
                FROM dispatchai.user_repositories ur
                JOIN dispatchai.repositories r ON ur.repo_id = r.id
                WHERE ur.user_id = %s
            """,
                (user_id,),
            )
            connected_repos = {f"{row[0]}/{row[1]}" for row in cur.fetchall()}

        conn.close()

        # Build response with repository information and sync status
        repository_responses = []
        for repo in repositories:
            full_name = repo["full_name"]
            sync_info = sync_data.get(full_name, {})

            repository_responses.append(
                RepositoryResponse(
                    owner=repo["owner"]["login"],
                    name=repo["name"],
                    full_name=full_name,
                    permissions={
                        "admin": repo["permissions"]["admin"],
                        "push": repo["permissions"]["push"],
                        "pull": repo["permissions"]["pull"],
                    },
                    connected=full_name in connected_repos,
                    last_sync_at=sync_info.get("last_sync_at"),
                    issues_synced=sync_info.get("issues_synced", 0),
                    sync_status=sync_info.get("sync_status"),
                )
            )

        logger.info(
            "Fetched organization repositories",
            user_id=user_id,
            org=org_login,
            count=len(repository_responses),
        )

        return OrganizationRepositoriesResponse(
            organization=org_login, repositories=repository_responses
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching organization repositories",
            user_id=current_user.get("sub"),
            org=org_login,
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Failed to fetch organization repositories"
        )


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
            correlation_id = None
            if message.headers:
                for key, value in message.headers:
                    if key == "correlation_id":
                        correlation_id = value.decode("utf-8")
                        break
            
            print(f"DEBUG: Processing message from {message.topic}, correlation_id={correlation_id}")

            event_data = json.loads(message.value.decode("utf-8"))

            websocket_message = {
                "type": "issue_update",
                "topic": message.topic,
                "timestamp": datetime.now().isoformat(),
                "data": event_data,
                "correlation_id": correlation_id,
            }

            # Extract repository info for filtering
            repo_owner = None
            repo_name = None
            if "issue" in event_data:
                repo_owner = event_data["issue"].get("repository_owner")
                repo_name = event_data["issue"].get("repository_name")

            # Create filter function for user access control
            def user_can_see_issue(user: Optional[Dict[str, Any]]) -> bool:
                if user is None:
                    return False

                if not repo_owner or not repo_name:
                    return True

                user_id = user.get("sub")
                if not user_id:
                    return False

                try:
                    conn = psycopg2.connect(DATABASE_URL)
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT 1 FROM dispatchai.user_repositories ur
                            JOIN dispatchai.repositories r ON ur.repo_id = r.id
                            WHERE ur.user_id = %s
                            AND r.owner = %s
                            AND r.name = %s
                            """,
                            (user_id, repo_owner, repo_name),
                        )
                        has_access = cur.fetchone() is not None
                    conn.close()
                    return has_access
                except Exception as e:
                    logger.error("Error checking user access", error=str(e))
                    return False

            print(
                f"DEBUG: Broadcasting to {len(self.manager.active_connections)} WebSocket clients with filtering"
            )

            await self.manager.broadcast(
                json.dumps(websocket_message), user_filter=user_can_see_issue
            )
            
            # Record metrics
            metrics.record_message_broadcast()

            print(f"DEBUG: Successfully broadcasted message from {message.topic}")

            logger.info(
                "Broadcasted Kafka message to authorized WebSocket clients",
                topic=message.topic,
                connected_clients=len(self.manager.active_connections),
                message_type=websocket_message["type"],
                repository=f"{repo_owner}/{repo_name}"
                if repo_owner and repo_name
                else None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            error_correlation_id = correlation_id if 'correlation_id' in locals() else None
            logger.error(
                "Error processing Kafka message",
                error=str(e),
                topic=message.topic if message else "unknown",
                correlation_id=error_correlation_id,
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
