"""
Auto-Triager Ingress Service
FastAPI webhook receiver for GitHub issues
"""
import hashlib
import hmac
import logging
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict

import structlog
from fastapi import FastAPI, Request, HTTPException, Header, status
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from kafka import KafkaProducer
import json

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

# Rate limiting middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm
    Limits webhook endpoints to prevent abuse
    """
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)  # IP -> list of timestamps
    
    async def dispatch(self, request: Request, call_next):
        # Only apply rate limiting to webhook endpoints
        if not request.url.path.startswith("/webhook"):
            return await call_next(request)
        
        # Get client IP (considering proxy headers)
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Clean old requests outside the window
        self.requests[client_ip] = [
            timestamp for timestamp in self.requests[client_ip]
            if current_time - timestamp < self.window_seconds
        ]
        
        # Check if rate limit exceeded
        if len(self.requests[client_ip]) >= self.max_requests:
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                requests_in_window=len(self.requests[client_ip]),
                max_requests=self.max_requests,
                window_seconds=self.window_seconds
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Too many webhook requests."
            )
        
        # Add current request timestamp
        self.requests[client_ip].append(current_time)
        
        # Process the request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = max(0, self.max_requests - len(self.requests[client_ip]))
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP considering proxy headers"""
        # Check common proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"

app = FastAPI(
    title="Auto-Triager Ingress Service",
    description="Webhook receiver for GitHub issues",
    version="0.1.0"
)

# Add rate limiting middleware
# Allow 100 webhook requests per minute per IP (configurable via env vars)
MAX_WEBHOOK_REQUESTS = int(os.getenv("MAX_WEBHOOK_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

app.add_middleware(
    RateLimitMiddleware,
    max_requests=MAX_WEBHOOK_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW
)

# Pydantic models for GitHub webhook payloads
class GitHubUser(BaseModel):
    id: int
    login: str
    avatar_url: str
    html_url: str

class GitHubRepository(BaseModel):
    id: int
    name: str
    full_name: str
    html_url: str
    description: Optional[str] = None
    private: bool
    owner: GitHubUser

class GitHubLabel(BaseModel):
    id: int
    name: str
    color: str
    description: Optional[str] = None

class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    labels: list[GitHubLabel] = []
    assignees: list[GitHubUser] = []
    created_at: datetime
    updated_at: datetime
    html_url: str

class GitHubComment(BaseModel):
    id: int
    body: str
    user: GitHubUser
    created_at: datetime
    updated_at: datetime
    html_url: str

class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    created_at: datetime
    updated_at: datetime
    html_url: str
    head: Dict[str, Any]
    base: Dict[str, Any]

class GitHubIssueWebhook(BaseModel):
    action: str
    issue: GitHubIssue
    repository: GitHubRepository
    sender: GitHubUser

class GitHubIssueCommentWebhook(BaseModel):
    action: str
    issue: GitHubIssue
    comment: GitHubComment
    repository: GitHubRepository
    sender: GitHubUser

class GitHubPullRequestWebhook(BaseModel):
    action: str
    pull_request: GitHubPullRequest
    repository: GitHubRepository
    sender: GitHubUser

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Environment configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
KAFKA_TOPIC_RAW_ISSUES = "issues.raw"

# Initialize Kafka producer for Redpanda
kafka_producer = None

def get_kafka_producer():
    """Get or create Kafka producer instance (works with Redpanda)"""
    global kafka_producer
    if kafka_producer is None:
        try:
            kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: str(k).encode('utf-8') if k else None,
                acks='all',
                retries=3,
                max_in_flight_requests_per_connection=1
            )
            logger.info("Kafka producer initialized for Redpanda", servers=KAFKA_BOOTSTRAP_SERVERS)
        except Exception as e:
            logger.error("Failed to initialize Kafka producer", error=str(e))
            raise
    return kafka_producer

def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC-SHA256
    """
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GitHub webhook secret not configured - skipping signature verification")
        return True
    
    if not signature_header:
        logger.error("Missing GitHub signature header")
        return False
    
    try:
        # GitHub sends signature as "sha256=<signature>"
        if not signature_header.startswith('sha256='):
            logger.error("Invalid signature format", signature=signature_header[:20])
            return False
        
        expected_signature = signature_header[7:]  # Remove "sha256=" prefix
        
        # Calculate expected signature
        calculated_signature = hmac.new(
            GITHUB_WEBHOOK_SECRET.encode('utf-8'),
            payload_body,
            hashlib.sha256
        ).hexdigest()
        
        # Secure comparison to prevent timing attacks
        is_valid = hmac.compare_digest(calculated_signature, expected_signature)
        
        if not is_valid:
            logger.error(
                "GitHub signature verification failed",
                expected_prefix=expected_signature[:10],
                calculated_prefix=calculated_signature[:10]
            )
        
        return is_valid
    
    except Exception as e:
        logger.error("Error verifying GitHub signature", error=str(e))
        return False

async def publish_to_kafka(topic: str, key: str, message: dict):
    """
    Publish message to Kafka/Redpanda topic
    """
    try:
        producer = get_kafka_producer()
        future = producer.send(topic, key=key, value=message)
        record_metadata = future.get(timeout=10)
        
        logger.info(
            "Message published to Kafka",
            topic=record_metadata.topic,
            partition=record_metadata.partition,
            offset=record_metadata.offset,
            key=key
        )
        
    except Exception as e:
        logger.error(
            "Failed to publish to Kafka",
            topic=topic,
            key=key,
            error=str(e)
        )
        raise

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="ingress",
        version="0.1.0"
    )

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """
    GitHub webhook endpoint for issues, issue comments, and pull requests
    Validates signatures and publishes events to Kafka/Redpanda
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify GitHub signature
        if not verify_github_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON payload", error=str(e))
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Get event type and validate
        event_type = x_github_event
        if not event_type:
            raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")
        
        # Log incoming webhook
        action = payload.get("action", "unknown")
        repository_name = payload.get("repository", {}).get("full_name", "unknown")
        
        logger.info(
            "Received GitHub webhook",
            event_type=event_type,
            action=action,
            repository=repository_name
        )
        
        # Process supported event types
        if event_type == "issues":
            webhook_data = GitHubIssueWebhook(**payload)
            event_data = {
                "event_type": "issue",
                "action": webhook_data.action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "repository": {
                    "id": webhook_data.repository.id,
                    "name": webhook_data.repository.name,
                    "full_name": webhook_data.repository.full_name,
                    "private": webhook_data.repository.private
                },
                "issue": {
                    "id": webhook_data.issue.id,
                    "number": webhook_data.issue.number,
                    "title": webhook_data.issue.title,
                    "body": webhook_data.issue.body,
                    "state": webhook_data.issue.state,
                    "labels": [{"name": label.name, "color": label.color} for label in webhook_data.issue.labels],
                    "created_at": webhook_data.issue.created_at.isoformat(),
                    "updated_at": webhook_data.issue.updated_at.isoformat(),
                    "html_url": webhook_data.issue.html_url,
                    "user": {
                        "id": webhook_data.issue.user.id,
                        "login": webhook_data.issue.user.login
                    }
                },
                "sender": {
                    "id": webhook_data.sender.id,
                    "login": webhook_data.sender.login
                }
            }
            
        elif event_type == "issue_comment":
            webhook_data = GitHubIssueCommentWebhook(**payload)
            event_data = {
                "event_type": "issue_comment",
                "action": webhook_data.action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "repository": {
                    "id": webhook_data.repository.id,
                    "name": webhook_data.repository.name,
                    "full_name": webhook_data.repository.full_name,
                    "private": webhook_data.repository.private
                },
                "issue": {
                    "id": webhook_data.issue.id,
                    "number": webhook_data.issue.number,
                    "title": webhook_data.issue.title,
                    "html_url": webhook_data.issue.html_url
                },
                "comment": {
                    "id": webhook_data.comment.id,
                    "body": webhook_data.comment.body,
                    "created_at": webhook_data.comment.created_at.isoformat(),
                    "html_url": webhook_data.comment.html_url,
                    "user": {
                        "id": webhook_data.comment.user.id,
                        "login": webhook_data.comment.user.login
                    }
                },
                "sender": {
                    "id": webhook_data.sender.id,
                    "login": webhook_data.sender.login
                }
            }
            
        elif event_type == "pull_request":
            webhook_data = GitHubPullRequestWebhook(**payload)
            event_data = {
                "event_type": "pull_request",
                "action": webhook_data.action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "repository": {
                    "id": webhook_data.repository.id,
                    "name": webhook_data.repository.name,
                    "full_name": webhook_data.repository.full_name,
                    "private": webhook_data.repository.private
                },
                "pull_request": {
                    "id": webhook_data.pull_request.id,
                    "number": webhook_data.pull_request.number,
                    "title": webhook_data.pull_request.title,
                    "body": webhook_data.pull_request.body,
                    "state": webhook_data.pull_request.state,
                    "created_at": webhook_data.pull_request.created_at.isoformat(),
                    "updated_at": webhook_data.pull_request.updated_at.isoformat(),
                    "html_url": webhook_data.pull_request.html_url,
                    "user": {
                        "id": webhook_data.pull_request.user.id,
                        "login": webhook_data.pull_request.user.login
                    }
                },
                "sender": {
                    "id": webhook_data.sender.id,
                    "login": webhook_data.sender.login
                }
            }
        else:
            logger.info("Unsupported event type", event_type=event_type)
            return {"status": "ignored", "reason": f"unsupported event type: {event_type}"}
        
        # Publish to Kafka/Redpanda
        message_key = f"{event_data['repository']['full_name']}:{event_data['event_type']}:{event_data.get('issue', event_data.get('pull_request', {})).get('number', 'unknown')}"
        
        await publish_to_kafka(KAFKA_TOPIC_RAW_ISSUES, message_key, event_data)
        
        logger.info(
            "Webhook processed successfully",
            event_type=event_type,
            action=action,
            repository=repository_name,
            message_key=message_key
        )
        
        return {
            "status": "accepted",
            "event_type": event_type,
            "action": action,
            "repository": repository_name,
            "message_key": message_key
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, auth failures)
        raise
    except Exception as e:
        logger.error(
            "Error processing webhook",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")

# Cleanup function for graceful shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    global kafka_producer
    if kafka_producer:
        try:
            kafka_producer.close()
            logger.info("Kafka producer closed")
        except Exception as e:
            logger.error("Error closing Kafka producer", error=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None  # Use structlog instead
    )
