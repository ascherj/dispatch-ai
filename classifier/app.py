"""
Auto-Triager Classifier Service
LangChain-powered issue classification and enrichment
"""
import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np

from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter

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
    title="Auto-Triager Classifier Service",
    description="LangChain-powered issue classification and enrichment",
    version="0.1.0"
)

# Pydantic models
class IssueData(BaseModel):
    id: int
    number: int
    title: str
    body: str
    labels: List[str]
    repository: str
    url: str
    created_at: str
    updated_at: str
    author: str

class ClassificationResult(BaseModel):
    issue_id: int
    category: str
    priority: str
    confidence: float
    tags: List[str]
    similar_issues: List[Dict[str, Any]]
    processing_time_ms: int

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ai_model: str

# Environment configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/auto_triager")
GATEWAY_SERVICE_URL = os.getenv("GATEWAY_SERVICE_URL", "http://gateway:8002")

# Initialize LangChain components
llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0.1,
    openai_api_key=OPENAI_API_KEY
) if OPENAI_API_KEY else None

# Classification prompt template
CLASSIFICATION_PROMPT = PromptTemplate(
    input_variables=["title", "body", "repository"],
    template="""
Analyze this GitHub issue and provide a classification:

Repository: {repository}
Title: {title}
Body: {body}

Please classify this issue with:
1. Category (bug, feature_request, documentation, question, enhancement, security)
2. Priority (low, medium, high, critical)
3. Confidence score (0.0 to 1.0)
4. Relevant tags (up to 5 descriptive tags)

Respond in JSON format:
{{
    "category": "category_name",
    "priority": "priority_level",
    "confidence": 0.95,
    "tags": ["tag1", "tag2", "tag3"],
    "reasoning": "Brief explanation of classification"
}}
"""
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if llm else "degraded",
        service="classifier",
        version="0.1.0",
        ai_model="gpt-3.5-turbo" if llm else "none"
    )

@app.post("/classify", response_model=ClassificationResult)
async def classify_issue(issue: IssueData):
    """
    Classify a GitHub issue using LangChain and OpenAI
    """
    start_time = datetime.now()

    try:
        logger.info(
            "Starting issue classification",
            issue_id=issue.id,
            issue_number=issue.number,
            repository=issue.repository
        )

        # Store raw issue in database
        await store_raw_issue(issue)

        # Perform classification
        if not llm:
            # Fallback classification without AI
            classification = fallback_classification(issue)
        else:
            # AI-powered classification
            classification = await ai_classification(issue)

        # Find similar issues
        similar_issues = await find_similar_issues(issue)

        # Store enriched issue
        await store_enriched_issue(issue, classification, similar_issues)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        result = ClassificationResult(
            issue_id=issue.id,
            category=classification["category"],
            priority=classification["priority"],
            confidence=classification["confidence"],
            tags=classification["tags"],
            similar_issues=similar_issues,
            processing_time_ms=int(processing_time)
        )

        logger.info(
            "Issue classification completed",
            issue_id=issue.id,
            category=result.category,
            priority=result.priority,
            confidence=result.confidence,
            processing_time_ms=result.processing_time_ms
        )

        return result

    except Exception as e:
        logger.error(
            "Error classifying issue",
            issue_id=issue.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Classification failed")

async def ai_classification(issue: IssueData) -> Dict[str, Any]:
    """Perform AI-powered classification using LangChain"""
    try:
        # Prepare the prompt
        prompt = CLASSIFICATION_PROMPT.format(
            title=issue.title,
            body=issue.body[:2000],  # Limit body length
            repository=issue.repository
        )

        # Get AI classification
        response = llm.invoke([HumanMessage(content=prompt)])

        # Parse JSON response
        classification = json.loads(response.content)

        return classification

    except json.JSONDecodeError:
        logger.warning("Failed to parse AI response, using fallback")
        return fallback_classification(issue)
    except Exception as e:
        logger.error("AI classification failed", error=str(e))
        return fallback_classification(issue)

def fallback_classification(issue: IssueData) -> Dict[str, Any]:
    """Fallback classification using keyword matching"""
    title_lower = issue.title.lower()
    body_lower = issue.body.lower()
    combined_text = f"{title_lower} {body_lower}"

    # Simple keyword-based classification
    if any(word in combined_text for word in ["bug", "error", "broken", "crash", "fail"]):
        category = "bug"
        priority = "high" if any(word in combined_text for word in ["crash", "critical", "urgent"]) else "medium"
    elif any(word in combined_text for word in ["feature", "enhancement", "improve", "add"]):
        category = "feature_request"
        priority = "medium"
    elif any(word in combined_text for word in ["doc", "documentation", "readme"]):
        category = "documentation"
        priority = "low"
    elif any(word in combined_text for word in ["question", "how", "help"]):
        category = "question"
        priority = "low"
    else:
        category = "enhancement"
        priority = "medium"

    # Generate simple tags
    tags = []
    if "ui" in combined_text or "interface" in combined_text:
        tags.append("ui")
    if "api" in combined_text:
        tags.append("api")
    if "database" in combined_text or "db" in combined_text:
        tags.append("database")
    if "performance" in combined_text:
        tags.append("performance")

    return {
        "category": category,
        "priority": priority,
        "confidence": 0.6,  # Lower confidence for fallback
        "tags": tags[:5],
        "reasoning": "Fallback keyword-based classification"
    }

async def store_raw_issue(issue: IssueData):
    """Store raw issue in database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO issues (id, number, title, body, labels, repository, url, created_at, updated_at, author, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    labels = EXCLUDED.labels,
                    updated_at = EXCLUDED.updated_at,
                    raw_data = EXCLUDED.raw_data
            """, (
                issue.id, issue.number, issue.title, issue.body,
                json.dumps(issue.labels), issue.repository, issue.url,
                issue.created_at, issue.updated_at, issue.author,
                json.dumps(issue.dict())
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to store raw issue", issue_id=issue.id, error=str(e))

async def store_enriched_issue(issue: IssueData, classification: Dict[str, Any], similar_issues: List[Dict[str, Any]]):
    """Store enriched issue with classification results"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO enriched_issues (issue_id, category, priority, confidence, tags, similar_issues, enriched_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (issue_id) DO UPDATE SET
                    category = EXCLUDED.category,
                    priority = EXCLUDED.priority,
                    confidence = EXCLUDED.confidence,
                    tags = EXCLUDED.tags,
                    similar_issues = EXCLUDED.similar_issues,
                    enriched_at = EXCLUDED.enriched_at
            """, (
                issue.id, classification["category"], classification["priority"],
                classification["confidence"], json.dumps(classification["tags"]),
                json.dumps(similar_issues)
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to store enriched issue", issue_id=issue.id, error=str(e))

async def find_similar_issues(issue: IssueData) -> List[Dict[str, Any]]:
    """Find similar issues using basic text similarity"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Simple similarity search based on title and repository
            cur.execute("""
                SELECT id, number, title, repository,
                       similarity(title, %s) as title_similarity
                FROM issues
                WHERE repository = %s AND id != %s
                ORDER BY title_similarity DESC
                LIMIT 5
            """, (issue.title, issue.repository, issue.id))

            similar = cur.fetchall()

        conn.close()

        return [
            {
                "id": row["id"],
                "number": row["number"],
                "title": row["title"],
                "similarity": float(row["title_similarity"]) if row["title_similarity"] else 0.0
            }
            for row in similar if row["title_similarity"] and row["title_similarity"] > 0.3
        ]

    except Exception as e:
        logger.error("Failed to find similar issues", error=str(e))
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_config=None
    )
