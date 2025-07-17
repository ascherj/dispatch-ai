#!/bin/bash

# Manual testing script for GitHub webhook endpoint
# Usage: ./test-webhook-manual.sh [endpoint_url]

set -e

ENDPOINT_URL=${1:-"http://localhost:8000"}
WEBHOOK_URL="$ENDPOINT_URL/webhook/github"

echo "🔗 Testing DispatchAI Webhook Endpoint"
echo "📍 URL: $WEBHOOK_URL"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to create GitHub signature
create_signature() {
    local payload="$1"
    local secret="$2"
    echo -n "$payload" | openssl dgst -sha256 -hmac "$secret" | cut -d' ' -f2
}

# Test 1: Health Check
echo -e "${BLUE}Test 1: Health Check${NC}"
curl -s -X GET "$ENDPOINT_URL/health" | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Health check completed${NC}"
echo ""

# Test 2: Valid GitHub Issues Webhook (No Signature)
echo -e "${BLUE}Test 2: Valid GitHub Issues Webhook (No Signature)${NC}"
ISSUE_PAYLOAD='{
  "action": "opened",
  "issue": {
    "id": 1234567890,
    "number": 123,
    "title": "Test Issue from Manual Script",
    "body": "This is a test issue created by the manual testing script.",
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
        "description": "Something is not working"
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
    "private": false,
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
}'

echo "Sending GitHub issues webhook..."
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d "$ISSUE_PAYLOAD" | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Issues webhook test completed${NC}"
echo ""

# Test 3: Valid GitHub Issue Comment Webhook
echo -e "${BLUE}Test 3: GitHub Issue Comment Webhook${NC}"
COMMENT_PAYLOAD='{
  "action": "created",
  "issue": {
    "id": 1234567890,
    "number": 123,
    "title": "Test Issue",
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
    "body": "This is a test comment from the manual testing script.",
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
    "private": false,
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
}'

echo "Sending GitHub issue comment webhook..."
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issue_comment" \
  -d "$COMMENT_PAYLOAD" | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Issue comment webhook test completed${NC}"
echo ""

# Test 4: Invalid Event Type
echo -e "${BLUE}Test 4: Unsupported Event Type${NC}"
echo "Testing unsupported event type..."
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: unsupported_event" \
  -d '{"action": "test"}' | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Unsupported event test completed${NC}"
echo ""

# Test 5: Missing Headers
echo -e "${BLUE}Test 5: Missing X-GitHub-Event Header${NC}"
echo "Testing missing X-GitHub-Event header..."
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"action": "test"}' | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Missing header test completed${NC}"
echo ""

# Test 6: Invalid JSON
echo -e "${BLUE}Test 6: Invalid JSON Payload${NC}"
echo "Testing invalid JSON..."
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d 'invalid json' | jq '.' || echo "jq not available, showing raw response"
echo -e "${GREEN}✅ Invalid JSON test completed${NC}"
echo ""

# Test 7: Rate Limiting Headers
echo -e "${BLUE}Test 7: Check Rate Limiting Headers${NC}"
echo "Checking rate limiting headers..."
curl -s -I -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d '{"action": "test"}' | grep -i "x-ratelimit" || echo "No rate limit headers found"
echo -e "${GREEN}✅ Rate limiting headers check completed${NC}"
echo ""

echo -e "${GREEN}🎉 All manual tests completed!${NC}"
echo ""
echo -e "${YELLOW}💡 Tips:${NC}"
echo "• Check container logs: docker logs dispatchai-ingress -f"
echo "• Monitor Kafka messages: make kafka-console"
echo "• View FastAPI docs: http://localhost:8000/docs"
echo "• View health status: http://localhost:8000/health"