"""
Auto-Triager Ingress Service
FastAPI webhook receiver for GitHub issues
"""
import logging
import os
from typing import Dict, Any

import structlog
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
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
    title="Auto-Triager Ingress Service",
    description="Webhook receiver for GitHub issues",
    version="0.1.0"
)

# Pydantic models for request validation
class GitHubIssuePayload(BaseModel):
    action: str
    issue: Dict[str, Any]
    repository: Dict[str, Any]
    sender: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

# Environment configuration
CLASSIFIER_SERVICE_URL = os.getenv("CLASSIFIER_SERVICE_URL", "http://classifier:8001")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

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
    background_tasks: BackgroundTasks,
    payload: GitHubIssuePayload
):
    """
    GitHub webhook endpoint for issue events
    Receives GitHub issue webhooks and forwards to classifier service
    """
    try:
        # Log incoming webhook
        logger.info(
            "Received GitHub webhook",
            action=payload.action,
            issue_number=payload.issue.get("number"),
            repository=payload.repository.get("full_name")
        )

        # Only process opened issues for now
        if payload.action not in ["opened", "edited"]:
            logger.info("Skipping webhook - not an opened/edited issue")
            return {"status": "ignored", "reason": "action not processed"}

        # Extract issue data
        issue_data = {
            "id": payload.issue["id"],
            "number": payload.issue["number"],
            "title": payload.issue["title"],
            "body": payload.issue.get("body", ""),
            "labels": [label["name"] for label in payload.issue.get("labels", [])],
            "repository": payload.repository["full_name"],
            "url": payload.issue["html_url"],
            "created_at": payload.issue["created_at"],
            "updated_at": payload.issue["updated_at"],
            "author": payload.issue["user"]["login"]
        }

        # Add background task to forward to classifier
        background_tasks.add_task(forward_to_classifier, issue_data)

        logger.info(
            "Webhook processed successfully",
            issue_id=issue_data["id"],
            issue_number=issue_data["number"]
        )

        return {
            "status": "accepted",
            "issue_id": issue_data["id"],
            "issue_number": issue_data["number"]
        }

    except Exception as e:
        logger.error(
            "Error processing webhook",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")

async def forward_to_classifier(issue_data: Dict[str, Any]):
    """
    Forward issue data to classifier service
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CLASSIFIER_SERVICE_URL}/classify",
                json=issue_data,
                timeout=30.0
            )
            response.raise_for_status()

        logger.info(
            "Successfully forwarded to classifier",
            issue_id=issue_data["id"],
            classifier_response_status=response.status_code
        )

    except httpx.RequestError as e:
        logger.error(
            "Failed to forward to classifier - connection error",
            issue_id=issue_data["id"],
            error=str(e)
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "Failed to forward to classifier - HTTP error",
            issue_id=issue_data["id"],
            status_code=e.response.status_code,
            error=str(e)
        )
    except Exception as e:
        logger.error(
            "Unexpected error forwarding to classifier",
            issue_id=issue_data["id"],
            error=str(e),
            exc_info=True
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None  # Use structlog instead
    )
