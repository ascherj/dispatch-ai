# Kafka Overview for DispatchAI

This document provides an overview of Apache Kafka technology and explains how it's integrated into the DispatchAI application.

## 🚀 What is Apache Kafka?

Apache Kafka is a distributed event streaming platform designed for high-throughput, fault-tolerant, real-time data processing. It acts as a message broker that can handle millions of events per second.

### Key Concepts

#### **Topics**
- Named streams of records (messages)
- Similar to database tables but for streaming data
- Example: `issues.raw`, `issues.enriched`

#### **Partitions**
- Topics are divided into partitions for scalability
- Each partition is an ordered, immutable sequence of records
- Enables parallel processing across multiple consumers

#### **Producers**
- Applications that publish (write) records to Kafka topics
- In DispatchAI: The ingress service publishes GitHub webhook events

#### **Consumers**
- Applications that subscribe to (read) records from Kafka topics
- In DispatchAI: The classifier service consumes raw events

#### **Brokers**
- Kafka servers that store and serve data
- Form a cluster for high availability and scalability

## 🔄 How Kafka Works

### Message Flow
```text
Producer → Kafka Topic (Partitioned) → Consumer
```

### Key Features

1. **Durability**: Messages are persisted to disk
2. **Scalability**: Horizontal scaling through partitioning
3. **Fault Tolerance**: Replication across multiple brokers
4. **Ordering**: Messages within a partition maintain order
5. **Real-time**: Low-latency message delivery

## 🏗️ Kafka Integration in DispatchAI

### Overview Architecture
```text
GitHub Webhook → Ingress Service → Kafka → Classifier Service → Kafka → Gateway Service
```

### Our Kafka Setup: Redpanda

We use **Redpanda** instead of traditional Apache Kafka:
- **Redpanda** is a Kafka-compatible streaming platform
- Written in C++ (vs Java for Kafka)
- Simpler deployment and operations
- Better performance for our use case
- Full Kafka API compatibility

### Topic Structure

#### **issues.raw**
- **Purpose**: Raw GitHub webhook events
- **Producer**: Ingress service (`/webhook/github` endpoint)
- **Consumer**: Classifier service
- **Partitions**: 3 (for parallel processing)
- **Retention**: Configurable (default: 7 days)

#### **issues.enriched**
- **Purpose**: AI-classified and enriched events
- **Producer**: Classifier service
- **Consumer**: Gateway service
- **Partitions**: 3 (matching raw events)
- **Retention**: Longer term (for analytics)

### Message Format

#### Raw Events (issues.raw)
```json
{
  "event_type": "issue",
  "action": "opened",
  "timestamp": "2023-12-01T10:00:00Z",
  "repository": {
    "id": 123456789,
    "name": "testrepo",
    "full_name": "testorg/testrepo",
    "private": false
  },
  "issue": {
    "id": 1234567890,
    "number": 123,
    "title": "Sample Issue Title",
    "body": "Issue description...",
    "state": "open",
    "labels": [...],
    "user": {...}
  },
  "sender": {...}
}
```

#### Enriched Events (issues.enriched)
```json
{
  "event_type": "issue",
  "action": "opened",
  "timestamp": "2023-12-01T10:00:00Z",
  "repository": {...},
  "issue": {...},
  "classification": {
    "category": "bug",
    "priority": "high",
    "effort_estimate": "medium",
    "suggested_assignee": "team-backend",
    "confidence": 0.85,
    "reasoning": "AI analysis explanation..."
  },
  "processing_metadata": {
    "processed_at": "2023-12-01T10:00:05Z",
    "processing_time_ms": 2340,
    "model_version": "gpt-4"
  }
}
```

### Message Keys

We use structured message keys for:
- **Partitioning**: Ensures related events go to same partition
- **Ordering**: Maintains chronological order per repository/issue
- **Debugging**: Easy identification of message streams

**Key Format**: `{repository_name}:{event_type}:{issue_number}`
**Example**: `testorg/testrepo:issue:123`

## 🔧 Implementation Details

### Producer Configuration (Ingress Service)

```python
# Location: ingress/app.py
kafka_producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    key_serializer=lambda k: str(k).encode('utf-8') if k else None,
    acks='all',  # Wait for all replicas to acknowledge
    retries=3,   # Retry failed sends
    max_in_flight_requests_per_connection=1  # Maintain ordering
)
```

### Publishing Messages

```python
# Publish to Kafka/Redpanda
message_key = f"{repository_name}:{event_type}:{issue_number}"
await publish_to_kafka(KAFKA_TOPIC_RAW_ISSUES, message_key, event_data)
```

### Consumer Configuration (Future: Classifier Service)

```python
# Future implementation
kafka_consumer = KafkaConsumer(
    'issues.raw',
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    key_deserializer=lambda k: k.decode('utf-8') if k else None,
    group_id='classifier-service',
    auto_offset_reset='earliest'
)
```

## 🛠️ Development & Operations

### Local Development

#### Start Redpanda
```bash
make dev  # Starts all services including Redpanda
```

#### Create Topics
```bash
make kafka-create-topics
```

#### List Topics
```bash
make kafka-topics
```

#### Monitor Messages
```bash
make kafka-console TOPIC=issues.raw
```

### Topic Management

#### Create Topic
```bash
docker exec dispatchai-redpanda rpk topic create issues.raw --partitions 3 --replicas 1
```

#### Consume Messages
```bash
docker exec dispatchai-redpanda rpk topic consume issues.raw --num 10
```

#### Topic Information
```bash
docker exec dispatchai-redpanda rpk topic describe issues.raw
```

### Monitoring

#### Check Redpanda Health
```bash
curl -s http://localhost:9644/v1/status/ready
```

#### Redpanda Console
- **Status**: Not currently configured in docker-compose
- **Available APIs**:
  - Admin API: http://localhost:9644
  - REST Proxy: http://localhost:18082
  - Schema Registry: http://localhost:18081

#### Adding Redpanda Console (Optional)
To add a web console, you could add this service to docker-compose.yml:

```yaml
redpanda-console:
  image: redpandadata/console:latest
  container_name: dispatchai-redpanda-console
  environment:
    - KAFKA_BROKERS=redpanda:9092
  ports:
    - "8080:8080"
  depends_on:
    - redpanda
  networks:
    - dispatchai-network
```

## 🔍 Benefits for DispatchAI

### 1. **Decoupling**
- Services can be developed, deployed, and scaled independently
- Ingress service doesn't need to know about classifier implementation

### 2. **Reliability**
- Messages are persisted and guaranteed delivery
- If classifier service is down, messages wait in the queue
- No data loss during service restarts

### 3. **Scalability**
- Multiple classifier instances can process events in parallel
- Partitioning enables horizontal scaling
- Can handle thousands of GitHub webhooks per second

### 4. **Observability**
- Message history for debugging and replay
- Processing metrics and monitoring
- Audit trail of all events

### 5. **Flexibility**
- Easy to add new consumers (analytics, notifications, etc.)
- Can replay events for testing or recovery
- Schema evolution support

## 🔮 Future Enhancements

### Multi-Consumer Architecture
```text
issues.raw → [Classifier Service]
          → [Analytics Service]
          → [Notification Service]
```

### Dead Letter Queues
```text
Failed Messages → issues.raw.dlq → Manual Review
```

### Event Sourcing
```text
All Events → Event Store → Rebuild Application State
```

## 🚨 Common Patterns & Best Practices

### 1. **Exactly-Once Processing**
- Use idempotent consumers
- Implement duplicate detection
- Transactional processing

### 2. **Error Handling**
- Retry policies for transient failures
- Dead letter queues for permanent failures
- Circuit breaker patterns

### 3. **Schema Management**
- Version your message schemas
- Backward compatibility considerations
- Schema registry for complex environments

### 4. **Performance Optimization**
- Batch processing for throughput
- Compression for large messages
- Proper partition key selection

## 📊 Monitoring & Troubleshooting

### Key Metrics to Monitor
- **Producer**: Send rate, error rate, latency
- **Consumer**: Lag, processing rate, errors
- **Broker**: Disk usage, memory, network I/O

### Common Issues
- **Consumer Lag**: Consumers can't keep up with producers
- **Partition Skew**: Uneven distribution across partitions
- **Rebalancing**: Consumer group coordination issues

### Troubleshooting Commands
```bash
# Check consumer group status
docker exec dispatchai-redpanda rpk group describe classifier-service

# Check topic lag
docker exec dispatchai-redpanda rpk group describe classifier-service --detailed

# View topic configuration
docker exec dispatchai-redpanda rpk topic describe issues.raw
```

## 📚 Additional Resources

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Redpanda Documentation](https://docs.redpanda.com/)
- [Kafka Patterns and Best Practices](https://kafka.apache.org/documentation/#design)

---

*This document provides a comprehensive overview of Kafka technology and its integration in the DispatchAI application. For implementation details, see the source code in the ingress/ directory.*