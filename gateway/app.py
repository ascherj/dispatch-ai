"""
Auto-Triager Gateway Service
WebSocket and REST API gateway for real-time communication
"""
import os
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import asyncio

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx

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
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = FastAPI(
    title="Auto-Triager Gateway Service",
    description="WebSocket and REST API gateway for real-time communication",
    version="0.1.0"
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

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    connected_clients: int

# Environment configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/auto_triager")
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
        logger.info("Client disconnected", total_connections=len(self.active_connections))

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        if self.active_connections:
            await asyncio.gather(
                *[connection.send_text(message) for connection in self.active_connections],
                return_exceptions=True
            )

manager = ConnectionManager()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="gateway",
        version="0.1.0",
        connected_clients=len(manager.active_connections)
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
    limit: int = 50
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
                where_conditions.append("i.repository = %s")
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
                    i.id, i.number, i.title, i.repository, i.created_at, i.updated_at,
                    e.category, e.priority, e.confidence, e.tags
                FROM issues i
                LEFT JOIN enriched_issues e ON i.id = e.issue_id
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
            issues.append(IssueResponse(
                id=row["id"],
                number=row["number"],
                title=row["title"],
                repository=row["repository"],
                category=row["category"],
                priority=row["priority"],
                confidence=row["confidence"],
                tags=json.loads(row["tags"]) if row["tags"] else [],
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
                status="classified" if row["category"] else "pending"
            ))

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
            cur.execute("""
                SELECT
                    i.id, i.number, i.title, i.body, i.repository, i.created_at, i.updated_at,
                    e.category, e.priority, e.confidence, e.tags, e.similar_issues
                FROM issues i
                LEFT JOIN enriched_issues e ON i.id = e.issue_id
                WHERE i.id = %s
            """, (issue_id,))

            row = cur.fetchone()

        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")

        return IssueResponse(
            id=row["id"],
            number=row["number"],
            title=row["title"],
            repository=row["repository"],
            category=row["category"],
            priority=row["priority"],
            confidence=row["confidence"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
            status="classified" if row["category"] else "pending"
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
            cur.execute("""
                SELECT id, number, title, body, labels, repository, url, created_at, updated_at, author
                FROM issues WHERE id = %s
            """, (issue_id,))

            issue_row = cur.fetchone()

        conn.close()

        if not issue_row:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Forward to classifier service
        async with httpx.AsyncClient() as client:
            classifier_url = os.getenv("CLASSIFIER_SERVICE_URL", "http://classifier:8001")

            issue_data = {
                "id": issue_row["id"],
                "number": issue_row["number"],
                "title": issue_row["title"],
                "body": issue_row["body"] or "",
                "labels": json.loads(issue_row["labels"]) if issue_row["labels"] else [],
                "repository": issue_row["repository"],
                "url": issue_row["url"],
                "created_at": issue_row["created_at"].isoformat(),
                "updated_at": issue_row["updated_at"].isoformat(),
                "author": issue_row["author"]
            }

            response = await client.post(
                f"{classifier_url}/classify",
                json=issue_data,
                timeout=60.0
            )
            response.raise_for_status()

            classification_result = response.json()

        # Broadcast update to connected clients
        await manager.broadcast(json.dumps({
            "type": "classification_update",
            "data": classification_result
        }))

        return {"status": "classification_triggered", "issue_id": issue_id}

    except httpx.RequestError as e:
        logger.error("Classifier service unavailable", error=str(e))
        raise HTTPException(status_code=503, detail="Classifier service unavailable")
    except Exception as e:
        logger.error("Error triggering classification", issue_id=issue_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to trigger classification")

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
                FROM issues i
                LEFT JOIN enriched_issues e ON i.id = e.issue_id
            """)
            counts = cur.fetchone()

            # Get category breakdown
            cur.execute("""
                SELECT category, COUNT(*) as count
                FROM enriched_issues
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
            """)
            categories = cur.fetchall()

            # Get priority breakdown
            cur.execute("""
                SELECT priority, COUNT(*) as count
                FROM enriched_issues
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
            "categories": [{"name": row["category"], "count": row["count"]} for row in categories],
            "priorities": [{"name": row["priority"], "count": row["count"]} for row in priorities],
            "connected_clients": len(manager.active_connections)
        }

    except Exception as e:
        logger.error("Error fetching stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")

# Serve static files for development
@app.get("/")
async def root():
    """Simple development landing page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Auto-Triager Gateway</title>
    </head>
    <body>
        <h1>Auto-Triager Gateway Service</h1>
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_config=None
    )
