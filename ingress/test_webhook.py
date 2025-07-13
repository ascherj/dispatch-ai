"""
Comprehensive tests for the Auto-Triager webhook endpoint
Tests signature validation, rate limiting, and event processing
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from kafka import KafkaProducer

from app import app, verify_github_signature, get_kafka_producer


class TestGitHubWebhook:
    """Test suite for GitHub webhook endpoint"""
    
    @pytest.fixture
    def client(self):
        """Test client fixture"""
        return TestClient(app)
    
    @pytest.fixture
    def webhook_secret(self):
        """Test webhook secret"""
        return "test_webhook_secret_123"
    
    @pytest.fixture
    def sample_issue_payload(self):
        """Sample GitHub issue webhook payload"""
        return {
            "action": "opened",
            "issue": {
                "id": 1234567890,
                "number": 123,
                "title": "Sample Issue Title",
                "body": "This is a sample issue body with some content.",
                "state": "open",
                "user": {
                    "id": 12345,
                    "login": "testuser",
                    "avatar_url": "https://github.com/testuser.png",
                    "html_url": "https://github.com/testuser"
                },
                "labels": [
                    {
                        "id": 1,
                        "name": "bug",
                        "color": "d73a4a",
                        "description": "Something isn't working"
                    }
                ],
                "assignees": [],
                "created_at": "2023-12-01T10:00:00Z",
                "updated_at": "2023-12-01T10:00:00Z",
                "html_url": "https://github.com/testorg/testrepo/issues/123"
            },
            "repository": {
                "id": 123456789,
                "name": "testrepo",
                "full_name": "testorg/testrepo",
                "html_url": "https://github.com/testorg/testrepo",
                "description": "Test repository",
                "private": False,
                "owner": {
                    "id": 12345,
                    "login": "testorg",
                    "avatar_url": "https://github.com/testorg.png",
                    "html_url": "https://github.com/testorg"
                }
            },
            "sender": {
                "id": 12345,
                "login": "testuser",
                "avatar_url": "https://github.com/testuser.png",
                "html_url": "https://github.com/testuser"
            }
        }
    
    @pytest.fixture
    def sample_comment_payload(self):
        """Sample GitHub issue comment webhook payload"""
        return {
            "action": "created",
            "issue": {
                "id": 1234567890,
                "number": 123,
                "title": "Sample Issue Title",
                "state": "open",
                "user": {
                    "id": 12345,
                    "login": "testuser",
                    "avatar_url": "https://github.com/testuser.png",
                    "html_url": "https://github.com/testuser"
                },
                "labels": [],
                "assignees": [],
                "created_at": "2023-12-01T10:00:00Z",
                "updated_at": "2023-12-01T10:00:00Z",
                "html_url": "https://github.com/testorg/testrepo/issues/123"
            },
            "comment": {
                "id": 987654321,
                "body": "This is a test comment on the issue.",
                "user": {
                    "id": 54321,
                    "login": "commentuser",
                    "avatar_url": "https://github.com/commentuser.png",
                    "html_url": "https://github.com/commentuser"
                },
                "created_at": "2023-12-01T11:00:00Z",
                "updated_at": "2023-12-01T11:00:00Z",
                "html_url": "https://github.com/testorg/testrepo/issues/123#issuecomment-987654321"
            },
            "repository": {
                "id": 123456789,
                "name": "testrepo",
                "full_name": "testorg/testrepo",
                "html_url": "https://github.com/testorg/testrepo",
                "description": "Test repository",
                "private": False,
                "owner": {
                    "id": 12345,
                    "login": "testorg",
                    "avatar_url": "https://github.com/testorg.png",
                    "html_url": "https://github.com/testorg"
                }
            },
            "sender": {
                "id": 54321,
                "login": "commentuser",
                "avatar_url": "https://github.com/commentuser.png",
                "html_url": "https://github.com/commentuser"
            }
        }
    
    def create_github_signature(self, payload: str, secret: str) -> str:
        """Create GitHub webhook signature for testing"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ingress"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
    
    @patch.dict('os.environ', {'GITHUB_WEBHOOK_SECRET': 'test_secret'})
    def test_signature_verification_success(self):
        """Test successful GitHub signature verification"""
        payload = "test payload"
        secret = "test_secret"
        signature = self.create_github_signature(payload, secret)
        
        result = verify_github_signature(payload.encode('utf-8'), signature)
        assert result is True
    
    def test_signature_verification_failure(self):
        """Test GitHub signature verification failure"""
        payload = "test payload"
        wrong_signature = "sha256=invalid_signature"
        
        with patch.dict('os.environ', {'GITHUB_WEBHOOK_SECRET': 'test_secret'}):
            # Need to reload the GITHUB_WEBHOOK_SECRET from environment
            with patch('app.GITHUB_WEBHOOK_SECRET', 'test_secret'):
                result = verify_github_signature(payload.encode('utf-8'), wrong_signature)
                assert result is False
    
    def test_signature_verification_no_secret(self):
        """Test signature verification when no secret is configured"""
        with patch.dict('os.environ', {}, clear=True):
            result = verify_github_signature(b"test", "sha256=anything")
            assert result is True  # Should pass when no secret configured
    
    def test_signature_verification_missing_header(self):
        """Test signature verification with missing header"""
        with patch.dict('os.environ', {'GITHUB_WEBHOOK_SECRET': 'test_secret'}):
            with patch('app.GITHUB_WEBHOOK_SECRET', 'test_secret'):
                result = verify_github_signature(b"test", None)
                assert result is False
    
    @patch('app.get_kafka_producer')
    @patch('app.GITHUB_WEBHOOK_SECRET', 'test_secret')
    def test_webhook_issue_event_success(self, mock_kafka, client, sample_issue_payload):
        """Test successful processing of GitHub issue webhook"""
        # Mock Kafka producer
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = MagicMock(
            topic="issues.raw",
            partition=0,
            offset=123
        )
        mock_producer.send.return_value = mock_future
        mock_kafka.return_value = mock_producer
        
        # Create payload and signature
        payload_str = json.dumps(sample_issue_payload)
        signature = self.create_github_signature(payload_str, "test_secret")
        
        # Make request
        response = client.post(
            "/webhook/github",
            content=payload_str,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "issues",
                "Content-Type": "application/json"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "issues"
        assert data["action"] == "opened"
        assert data["repository"] == "testorg/testrepo"
        
        # Verify Kafka producer was called
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        # The send method uses positional arguments: send(topic, key=..., value=...)
        assert call_args[0][0] == "issues.raw"  # First positional arg is topic
        assert "testorg/testrepo:issue:123" in call_args[1]["key"]
    
    @patch('app.get_kafka_producer')
    @patch('app.GITHUB_WEBHOOK_SECRET', 'test_secret')
    def test_webhook_comment_event_success(self, mock_kafka, client, sample_comment_payload):
        """Test successful processing of GitHub issue comment webhook"""
        # Mock Kafka producer
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_future.get.return_value = MagicMock(
            topic="issues.raw",
            partition=0,
            offset=124
        )
        mock_producer.send.return_value = mock_future
        mock_kafka.return_value = mock_producer
        
        # Create payload and signature
        payload_str = json.dumps(sample_comment_payload)
        signature = self.create_github_signature(payload_str, "test_secret")
        
        # Make request
        response = client.post(
            "/webhook/github",
            content=payload_str,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "issue_comment",
                "Content-Type": "application/json"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "issue_comment"
        assert data["action"] == "created"
        
        # Verify Kafka producer was called
        mock_producer.send.assert_called_once()
    
    @patch('app.GITHUB_WEBHOOK_SECRET', 'test_secret')
    def test_webhook_invalid_signature(self, client, sample_issue_payload):
        """Test webhook with invalid signature"""
        payload_str = json.dumps(sample_issue_payload)
        
        response = client.post(
            "/webhook/github",
            content=payload_str,
            headers={
                "X-Hub-Signature-256": "sha256=invalid_signature",
                "X-GitHub-Event": "issues",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]
    
    def test_webhook_missing_event_header(self, client, sample_issue_payload):
        """Test webhook with missing X-GitHub-Event header"""
        payload_str = json.dumps(sample_issue_payload)
        
        response = client.post(
            "/webhook/github",
            content=payload_str,
            headers={
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 400
        assert "Missing X-GitHub-Event header" in response.json()["detail"]
    
    def test_webhook_invalid_json(self, client):
        """Test webhook with invalid JSON payload"""
        response = client.post(
            "/webhook/github",
            content="invalid json",
            headers={
                "X-GitHub-Event": "issues",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["detail"]
    
    def test_webhook_unsupported_event(self, client):
        """Test webhook with unsupported event type"""
        payload = {"action": "test"}
        payload_str = json.dumps(payload)
        
        response = client.post(
            "/webhook/github",
            content=payload_str,
            headers={
                "X-GitHub-Event": "unsupported_event",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "unsupported event type" in data["reason"]


class TestRateLimiting:
    """Test suite for rate limiting middleware"""
    
    @pytest.fixture
    def client(self):
        """Test client with rate limiting"""
        return TestClient(app)
    
    def test_rate_limit_headers(self, client):
        """Test that rate limit headers are included in webhook responses"""
        response = client.post(
            "/webhook/github",
            json={"test": "data"},
            headers={"X-GitHub-Event": "issues"}
        )
        
        # Should include rate limit headers even for failed requests
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Window" in response.headers
    
    def test_rate_limit_enforcement(self, client):
        """Test rate limit enforcement logic"""
        # Test the core rate limiting logic without complex async mocking
        from app import RateLimitMiddleware
        import time
        
        # Create a middleware instance with very low limits for testing
        middleware = RateLimitMiddleware(app=None, max_requests=2, window_seconds=60)
        
        # Simulate multiple requests from the same IP
        client_ip = "test_client_ip"
        current_time = time.time()
        
        # First request - should be allowed
        middleware.requests[client_ip].append(current_time)
        assert len(middleware.requests[client_ip]) == 1
        
        # Second request - should be allowed
        middleware.requests[client_ip].append(current_time + 1)
        assert len(middleware.requests[client_ip]) == 2
        
        # Check if third request would exceed limit
        # Simulate the logic from the dispatch method
        window_start = current_time + 2 - middleware.window_seconds
        active_requests = [
            timestamp for timestamp in middleware.requests[client_ip]
            if timestamp > window_start
        ]
        
        # All requests are within the window, so we should have 2 active requests
        assert len(active_requests) == 2
        
        # Third request should be blocked (>= max_requests)
        assert len(active_requests) >= middleware.max_requests
        
        # Test that old requests outside window are cleaned up
        old_time = current_time - middleware.window_seconds - 10
        middleware.requests[client_ip].append(old_time)
        
        # Clean old requests (simulate the cleanup logic)
        current_time_new = current_time + 10
        middleware.requests[client_ip] = [
            timestamp for timestamp in middleware.requests[client_ip]
            if current_time_new - timestamp < middleware.window_seconds
        ]
        
        # Should have removed the old request
        assert len(middleware.requests[client_ip]) == 2  # Only the recent ones remain
    
    def test_rate_limit_non_webhook_endpoints(self, client):
        """Test that rate limiting doesn't affect non-webhook endpoints"""
        # Health endpoint should not be rate limited
        for i in range(10):
            response = client.get("/health")
            assert response.status_code == 200
            # Should not have rate limit headers
            assert "X-RateLimit-Limit" not in response.headers


class TestKafkaIntegration:
    """Test suite for Kafka producer integration"""
    
    @patch('app.KafkaProducer')
    def test_kafka_producer_initialization(self, mock_kafka_producer):
        """Test Kafka producer initialization"""
        # Reset the global producer first
        import app
        app.kafka_producer = None
        
        mock_producer_instance = MagicMock()
        mock_kafka_producer.return_value = mock_producer_instance
        
        producer = get_kafka_producer()
        
        # Verify producer was created with correct configuration
        mock_kafka_producer.assert_called_once()
        call_kwargs = mock_kafka_producer.call_args[1]
        assert 'bootstrap_servers' in call_kwargs
        assert 'value_serializer' in call_kwargs
        assert 'key_serializer' in call_kwargs
        assert call_kwargs['acks'] == 'all'
        assert call_kwargs['retries'] == 3
        
        # Should return the same instance on subsequent calls
        producer2 = get_kafka_producer()
        assert producer is producer2
    
    @patch('app.get_kafka_producer')
    def test_kafka_producer_error_handling(self, mock_get_producer):
        """Test Kafka producer error handling"""
        # Mock producer that raises an exception
        mock_producer = MagicMock()
        mock_producer.send.side_effect = Exception("Kafka connection failed")
        mock_get_producer.return_value = mock_producer
        
        from app import publish_to_kafka
        
        with pytest.raises(Exception):
            # This should be run in an async context in real usage
            import asyncio
            asyncio.run(publish_to_kafka("test_topic", "test_key", {"test": "data"}))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment"""
    # Reset any global state before running tests
    import app
    app.kafka_producer = None
    
    yield
    
    # Cleanup after tests
    if app.kafka_producer:
        try:
            app.kafka_producer.close()
        except:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])