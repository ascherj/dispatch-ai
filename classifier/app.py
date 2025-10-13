"""
DispatchAI Classifier Service
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

from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import HumanMessage
from kafka import KafkaConsumer, KafkaProducer
import asyncio
import threading

# Configure structured logging with INFO level
import logging

logging.basicConfig(level=logging.INFO)

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
    title="DispatchAI Classifier Service",
    description="LangChain-powered issue classification and enrichment",
    version="0.1.0",
)


# Metrics tracking
class ServiceMetrics:
    """In-memory metrics tracking for observability"""
    def __init__(self):
        self.start_time = datetime.now()
        self.issues_processed = 0
        self.openai_api_errors = 0
        self.classification_times_ms = []
        
    def record_issue_processed(self):
        self.issues_processed += 1
    
    def record_openai_error(self):
        self.openai_api_errors += 1
    
    def record_classification_time(self, duration_ms: float):
        self.classification_times_ms.append(duration_ms)
        # Keep only last 1000 measurements
        if len(self.classification_times_ms) > 1000:
            self.classification_times_ms = self.classification_times_ms[-1000:]
    
    def get_percentile(self, percentile: int) -> float:
        """Calculate percentile from classification times"""
        if not self.classification_times_ms:
            return 0.0
        sorted_times = sorted(self.classification_times_ms)
        index = int(len(sorted_times) * percentile / 100)
        return round(sorted_times[min(index, len(sorted_times) - 1)], 2)
    
    def get_uptime_seconds(self) -> int:
        return int((datetime.now() - self.start_time).total_seconds())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": "classifier",
            "issues_processed": self.issues_processed,
            "classification_time_ms": {
                "p50": self.get_percentile(50),
                "p95": self.get_percentile(95),
                "p99": self.get_percentile(99),
            },
            "openai_api_errors": self.openai_api_errors,
            "uptime_seconds": self.get_uptime_seconds(),
        }

metrics = ServiceMetrics()


def get_kafka_producer():
    """Get or create Kafka producer instance"""
    global kafka_producer
    if kafka_producer is None:
        kafka_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: str(k).encode("utf-8") if k else None,
            acks="all",  # Reliability
            retries=3,  # Fault tolerance
            max_in_flight_requests_per_connection=1,  # Ordering guarantee
        )
        logger.info(
            "Kafka producer initialized", bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS
        )
    return kafka_producer


# Pydantic models
class IssueData(BaseModel):
    id: int
    number: int
    title: str
    body: Optional[str] = ""  # Allow None/null body, default to empty string
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
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
GATEWAY_SERVICE_URL = os.getenv("GATEWAY_SERVICE_URL", "http://gateway:8002")

# Log environment variable status for debugging
logger.info(
    "Environment variables loaded",
    openai_api_key_configured=bool(OPENAI_API_KEY),
    openai_key_preview=OPENAI_API_KEY[:10] if OPENAI_API_KEY else "None",
    database_url=DATABASE_URL,
    kafka_servers=KAFKA_BOOTSTRAP_SERVERS,
)

# Global Kafka producer instance
kafka_producer = None

# Initialize LangChain components
llm = (
    ChatOpenAI(
        model="gpt-4o-mini",  # Better reasoning, cheaper than gpt-3.5-turbo
        temperature=0.1,
        openai_api_key=OPENAI_API_KEY,
    )
    if OPENAI_API_KEY
    else None
)

# Initialize OpenAI embeddings
embeddings = (
    OpenAIEmbeddings(
        openai_api_key=OPENAI_API_KEY,
        model="text-embedding-3-small",  # Better performance, cheaper than ada-002
    )
    if OPENAI_API_KEY
    else None
)

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
""",
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if llm else "degraded",
        service="classifier",
        version="0.1.0",
        ai_model="gpt-4o-mini" if llm else "none",
    )


@app.get("/metrics")
async def get_metrics():
    """Expose operational metrics for monitoring"""
    return metrics.to_dict()


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
        finally:
            kafka_producer = None


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
            repository=issue.repository,
        )

        # Store raw issue in database
        await store_raw_issue(issue)

        # Perform classification
        if not llm:
            logger.warning("No LLM model available, using fallback classification")
            # Fallback classification without AI
            classification = fallback_classification(issue)
        else:
            # AI-powered classification
            classification = await ai_classification(issue)

        # Generate embeddings
        embedding = await generate_embedding(issue)

        # Find similar issues
        similar_issues = await find_similar_issues(issue, embedding)

        # Store enriched issue
        await store_enriched_issue(issue, classification, similar_issues, embedding)

        # Publish enriched issue to Kafka for real-time updates
        await publish_enriched_issue(issue, classification, similar_issues)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        result = ClassificationResult(
            issue_id=issue.id,
            category=classification["category"],
            priority=classification["priority"],
            confidence=classification["confidence"],
            tags=classification["tags"],
            similar_issues=similar_issues,
            processing_time_ms=int(processing_time),
        )

        logger.info(
            "Issue classification completed",
            issue_id=issue.id,
            category=result.category,
            priority=result.priority,
            confidence=result.confidence,
            processing_time_ms=result.processing_time_ms,
        )
        
        # Record metrics
        metrics.record_issue_processed()
        metrics.record_classification_time(result.processing_time_ms)

        return result

    except Exception as e:
        logger.error(
            "Error classifying issue", issue_id=issue.id, error=str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="Classification failed")


async def ai_classification(issue: IssueData) -> Dict[str, Any]:
    """Perform AI-powered classification using LangChain"""
    try:
        # Prepare the prompt
        prompt = CLASSIFICATION_PROMPT.format(
            title=issue.title,
            body=(issue.body or "")[:2000],  # Handle null body, limit body length
            repository=issue.repository,
        )

        # Get AI classification
        response = llm.invoke([HumanMessage(content=prompt)])

        # Parse JSON response - strip markdown code blocks if present
        response_text = response.content.strip()
        if response_text.startswith("```json\n") and response_text.endswith("\n```"):
            response_text = response_text[8:-4]  # Remove ```json\n and \n```
        elif response_text.startswith("```\n") and response_text.endswith("\n```"):
            response_text = response_text[4:-4]  # Remove ```\n and \n```

        logger.debug(
            "AI response content", response_content=response.content[:500]
        )  # Log first 500 chars
        classification = json.loads(response_text)

        return classification

    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse AI response, using fallback",
            response_content=response.content[:500],
        )
        metrics.record_openai_error()
        return fallback_classification(issue)
    except Exception as e:
        logger.error("AI classification failed", error=str(e))
        metrics.record_openai_error()
        return fallback_classification(issue)


def fallback_classification(issue: IssueData) -> Dict[str, Any]:
    """Fallback classification using keyword matching"""
    title_lower = issue.title.lower()
    body_lower = (issue.body or "").lower()  # Handle null body
    combined_text = f"{title_lower} {body_lower}"

    # Simple keyword-based classification
    if any(
        word in combined_text for word in ["bug", "error", "broken", "crash", "fail"]
    ):
        category = "bug"
        priority = (
            "high"
            if any(word in combined_text for word in ["crash", "critical", "urgent"])
            else "medium"
        )
    elif any(
        word in combined_text for word in ["feature", "enhancement", "improve", "add"]
    ):
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
        "reasoning": "Fallback keyword-based classification",
    }


async def store_raw_issue(issue: IssueData):
    """Store raw issue in database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dispatchai.issues (
                    github_issue_id, repository_name, repository_owner, issue_number,
                    title, body, state, labels, assignees, author, created_at, updated_at, raw_data
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (github_issue_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    labels = EXCLUDED.labels,
                    updated_at = EXCLUDED.updated_at,
                    raw_data = EXCLUDED.raw_data
            """,
                (
                    issue.id,
                    issue.repository.split("/")[-1],
                    issue.repository.split("/")[0],
                    issue.number,
                    issue.title,
                    issue.body,
                    "open",
                    json.dumps(issue.labels),
                    json.dumps([]),
                    issue.author,
                    issue.created_at,
                    issue.updated_at,
                    json.dumps(issue.dict()),
                ),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to store raw issue", issue_id=issue.id, error=str(e))


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
            # First, get the internal issue ID from the issues table
            cur.execute(
                """
                SELECT id FROM dispatchai.issues
                WHERE github_issue_id = %s
            """,
                (issue.id,),
            )
            result = cur.fetchone()
            if not result:
                logger.error("Issue not found in database", github_issue_id=issue.id)
                return

            internal_issue_id = result[0]

            # Store enriched data (use upsert since there's no unique constraint on issue_id)
            cur.execute(
                """
                INSERT INTO dispatchai.enriched_issues (
                    issue_id, classification, summary, tags, suggested_assignees,
                    estimated_effort, category, priority, severity, component, sentiment,
                    embedding, confidence_score, processing_model, ai_reasoning
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    internal_issue_id,
                    json.dumps(classification),
                    classification.get("summary", ""),
                    classification.get("tags", []),
                    classification.get("suggested_assignees", []),
                    classification.get("estimated_effort", "medium"),
                    classification.get("category", "unknown"),
                    classification.get("priority", "medium"),
                    classification.get("severity", "minor"),
                    classification.get("component", "unknown"),
                    classification.get("sentiment", "neutral"),
                    embedding,
                    classification.get("confidence", 0.0),
                    "gpt-4o-mini",
                    classification.get("reasoning", ""),
                ),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to store enriched issue", issue_id=issue.id, error=str(e))


async def publish_enriched_issue(
    issue: IssueData,
    classification: Dict[str, Any],
    similar_issues: List[Dict[str, Any]] = None,
):
    """Publish enriched issue to Kafka for real-time updates"""
    try:
        producer = get_kafka_producer()

        # Create enriched event payload
        enriched_data = {
            "issue": {
                "id": issue.id,
                "number": issue.number,
                "title": issue.title,
                "body": issue.body,
                "repository": issue.repository,
                "url": issue.url,
                "author": issue.author,
                "labels": issue.labels,
                "created_at": issue.created_at,
                "updated_at": issue.updated_at,
            },
            "classification": {
                "category": classification.get("category"),
                "priority": classification.get("priority"),
                "confidence": classification.get("confidence"),
                "tags": classification.get("tags", []),
                "summary": classification.get("summary", ""),
                "reasoning": classification.get("reasoning", ""),
                "estimated_effort": classification.get("estimated_effort", "medium"),
                "component": classification.get("component", "unknown"),
                "sentiment": classification.get("sentiment", "neutral"),
            },
            "similar_issues": similar_issues or [],
            "processed_at": datetime.now().isoformat(),
            "processing_model": "gpt-4o-mini",
            "event_type": "issue_classified",
        }

        # Create message key for partitioning
        message_key = f"{issue.repository}:issue:{issue.number}"

        # Send to Kafka
        future = producer.send("issues.enriched", key=message_key, value=enriched_data)

        # Wait for message to be sent (with timeout)
        record_metadata = future.get(timeout=10)

        logger.info(
            "Published enriched issue to Kafka",
            issue_id=issue.id,
            repository=issue.repository,
            topic=record_metadata.topic,
            partition=record_metadata.partition,
            offset=record_metadata.offset,
        )

    except Exception as e:
        logger.error(
            "Failed to publish enriched issue to Kafka", issue_id=issue.id, error=str(e)
        )
        # Don't raise the exception - Kafka publishing should not fail the classification


async def generate_embedding(issue: IssueData) -> Optional[List[float]]:
    """Generate OpenAI embedding for the issue"""
    try:
        if not embeddings:
            return None

        # Combine title and body for embedding
        text = f"{issue.title}\n\n{issue.body[:2000]}"  # Limit to avoid token limits

        # Generate embedding
        embedding_vector = await asyncio.get_event_loop().run_in_executor(
            None, embeddings.embed_query, text
        )

        return embedding_vector

    except Exception as e:
        logger.error("Failed to generate embedding", issue_id=issue.id, error=str(e))
        return None


async def find_similar_issues(
    issue: IssueData, issue_embedding: Optional[List[float]] = None
) -> List[Dict[str, Any]]:
    """Find similar issues using vector similarity search"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if issue_embedding:
                # Vector similarity search
                cur.execute(
                    """
                    SELECT i.id, i.issue_number, i.title, i.repository_name,
                           ei.embedding <-> %s as similarity_distance
                    FROM dispatchai.issues i
                    JOIN dispatchai.enriched_issues ei ON i.id = ei.issue_id
                    WHERE i.repository_name = %s AND i.github_issue_id != %s
                    AND ei.embedding IS NOT NULL
                    ORDER BY similarity_distance ASC
                    LIMIT 5
                """,
                    (issue_embedding, issue.repository.split("/")[-1], issue.id),
                )
            else:
                # Fallback to text similarity
                cur.execute(
                    """
                    SELECT i.id, i.issue_number, i.title, i.repository_name,
                           similarity(i.title, %s) as title_similarity
                    FROM dispatchai.issues i
                    WHERE i.repository_name = %s AND i.github_issue_id != %s
                    ORDER BY title_similarity DESC
                    LIMIT 5
                """,
                    (issue.title, issue.repository.split("/")[-1], issue.id),
                )

            similar = cur.fetchall()

        conn.close()

        return [
            {
                "id": row["id"],
                "number": row["issue_number"],
                "title": row["title"],
                "similarity": float(1 - row["similarity_distance"])
                if issue_embedding and row["similarity_distance"]
                else float(row.get("title_similarity", 0.0)),
            }
            for row in similar
            if (
                issue_embedding
                and row["similarity_distance"]
                and row["similarity_distance"] < 0.5
            )
            or (not issue_embedding and row.get("title_similarity", 0) > 0.3)
        ]

    except Exception as e:
        logger.error("Failed to find similar issues", error=str(e))
        return []


# Kafka consumer for processing issue events
async def process_kafka_message(message):
    """Process a Kafka message containing issue data"""
    try:
        correlation_id = None
        if message.headers:
            for key, value in message.headers:
                if key == "correlation_id":
                    correlation_id = value.decode("utf-8")
                    break
        
        bound_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
        
        # Parse the message
        issue_data = json.loads(message.value.decode("utf-8"))

        bound_logger.info(
            "Received Kafka message for classification",
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
        )

        # Convert to IssueData model
        issue = IssueData(
            id=issue_data.get("issue", {}).get("id"),
            number=issue_data.get("issue", {}).get("number"),
            title=issue_data.get("issue", {}).get("title", ""),
            body=issue_data.get("issue", {}).get("body", ""),
            labels=[
                label.get("name", "")
                for label in issue_data.get("issue", {}).get("labels", [])
            ],
            repository=issue_data.get("repository", {}).get("full_name", ""),
            url=issue_data.get("issue", {}).get("html_url", ""),
            created_at=issue_data.get("issue", {}).get("created_at", ""),
            updated_at=issue_data.get("issue", {}).get("updated_at", ""),
            author=issue_data.get("issue", {}).get("user", {}).get("login", ""),
        )

        # Process the issue
        await classify_issue(issue)

        bound_logger.info(
            "Processed Kafka message",
            issue_id=issue.id,
            issue_number=issue.number,
            repository=issue.repository,
        )

    except Exception as e:
        error_correlation_id = correlation_id if 'correlation_id' in locals() else None
        logger.error(
            "Failed to process Kafka message", error=str(e), message=message.value, correlation_id=error_correlation_id
        )


def kafka_consumer_thread():
    """Run Kafka consumer in a separate thread"""
    try:
        consumer = KafkaConsumer(
            "issues.raw",
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_deserializer=lambda m: m,
            group_id="dispatchai-classifier",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            # Removed consumer_timeout_ms to keep consumer running indefinitely
        )

        logger.info("Kafka consumer started", topic="issues.raw")

        for message in consumer:
            try:
                # Run the async processing in the event loop
                asyncio.run(process_kafka_message(message))
            except Exception as e:
                logger.error("Error processing Kafka message", error=str(e))

    except Exception as e:
        logger.error("Kafka consumer error", error=str(e))


# Always start Kafka consumer when the app module is loaded
kafka_thread = threading.Thread(target=kafka_consumer_thread, daemon=True)
kafka_thread.start()
logger.info("Started Kafka consumer thread")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True, log_config=None)
