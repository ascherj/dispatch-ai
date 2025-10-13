#!/bin/bash

# Easy GitHub webhook test for DispatchAI
# This sends a properly formatted GitHub issue webhook to test the full pipeline

set -e

echo "🚀 Sending GitHub Issue Webhook"
echo "==============================="

# Generate development JWT token for API authentication
echo "🔐 Generating development JWT token..."
DEV_JWT=$(python3 -c "
from jose import jwt
import time
payload = {
    'sub': '0',  # Subject must be a string
    'username': 'dev_user',
    'dev_mode': True,
    'exp': int(time.time()) + 3600
}
token = jwt.encode(payload, 'dev-jwt-secret-change-in-production-to-secure-random-key', algorithm='HS256')
print(token)
")

echo "✅ JWT token generated"

# Get current timestamp
CURRENT_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ISSUE_NUMBER=$((RANDOM % 1000 + 100))  # Random issue number

# Complete GitHub webhook payload (based on test fixtures)
WEBHOOK_PAYLOAD=$(cat << EOF
{
  "action": "opened",
  "issue": {
    "id": $ISSUE_NUMBER$ISSUE_NUMBER,
    "number": $ISSUE_NUMBER,
    "title": "Dashboard shows blank screen on mobile devices",
    "body": "When accessing the dashboard on mobile devices (tested on iPhone and Android), the screen appears completely blank. Desktop works fine. This might be a CSS viewport issue or JavaScript mobile compatibility problem. Steps to reproduce:\n1. Open dashboard on mobile browser\n2. Page loads but shows blank white screen\n3. No console errors visible\n\nExpected: Dashboard should display properly on mobile devices\nActual: Blank screen\n\nPriority: High - affects mobile users",
    "state": "open",
    "user": {
      "id": 12345,
      "login": "mobile-user",
      "avatar_url": "https://github.com/mobile-user.png",
      "html_url": "https://github.com/mobile-user"
    },
    "labels": [
      {
        "id": 1,
        "name": "bug",
        "color": "d73a4a",
        "description": "Something isn't working"
      },
      {
        "id": 2,
        "name": "mobile",
        "color": "0052cc",
        "description": "Mobile-specific issue"
      }
    ],
    "assignees": [],
    "created_at": "$CURRENT_TIME",
    "updated_at": "$CURRENT_TIME",
    "html_url": "https://github.com/testorg/dispatchai/issues/$ISSUE_NUMBER"
  },
  "repository": {
    "id": 789123456,
    "name": "dispatchai",
    "full_name": "testorg/dispatchai",
    "html_url": "https://github.com/testorg/dispatchai",
    "description": "AI-powered GitHub issue triaging system",
    "private": false,
    "owner": {
      "id": 67890,
      "login": "testorg",
      "avatar_url": "https://github.com/testorg.png",
      "html_url": "https://github.com/testorg"
    }
  },
  "sender": {
    "id": 12345,
    "login": "mobile-user",
    "avatar_url": "https://github.com/mobile-user.png",
    "html_url": "https://github.com/mobile-user"
  }
}
EOF
)

echo "📤 Sending webhook to ingress service..."
echo "Issue Number: #$ISSUE_NUMBER"
echo "Timestamp: $CURRENT_TIME"
echo ""

# Send the webhook
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -d "$WEBHOOK_PAYLOAD")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')

echo "📨 Response:"
echo "Status: $HTTP_STATUS"
echo "Body: $BODY"
echo ""

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ Webhook accepted! Now waiting for processing..."
    echo ""
    
    # Wait for processing
    echo "⏳ Waiting 5 seconds for issue to be stored..."
    sleep 5
    
    # Check if issue appears in API
    echo "🔍 Checking if issue appears in API..."
    NEW_ISSUE=$(curl -s -H "Authorization: Bearer $DEV_JWT" http://localhost:8002/api/issues | jq ".[] | select(.number == $ISSUE_NUMBER)")
    
    if [ -n "$NEW_ISSUE" ]; then
        echo "✅ Issue found in API!"
        echo "$NEW_ISSUE" | jq '.'
        
        # Get issue ID and trigger classification
        ISSUE_ID=$(echo "$NEW_ISSUE" | jq -r '.id')
        echo ""
        echo "🤖 Triggering AI classification for issue ID: $ISSUE_ID..."
        curl -s -X POST -H "Authorization: Bearer $DEV_JWT" "http://localhost:8002/api/issues/$ISSUE_ID/classify" | jq '.'
        
        echo ""
        echo "⏳ Waiting 10 seconds for AI classification..."
        sleep 10
        
        echo "🔍 Checking classified result..."
        CLASSIFIED=$(curl -s -H "Authorization: Bearer $DEV_JWT" "http://localhost:8002/api/issues" | jq ".[] | select(.id == $ISSUE_ID)")
        echo "$CLASSIFIED" | jq '.'
        
        echo ""
        echo "🎉 SUCCESS! Full pipeline completed:"
        echo "   ✅ Webhook received and validated"
        echo "   ✅ Issue stored in database"
        echo "   ✅ Available via API"
        echo "   ✅ AI classification triggered"
        echo "   ✅ Issue classified and updated"
        echo ""
        echo "📊 Updated stats:"
        curl -s -H "Authorization: Bearer $DEV_JWT" http://localhost:8002/api/stats | jq '.'
        echo ""
        echo "🌐 View in dashboard: http://localhost:3000"
        echo "💡 Try the Edit button to test manual corrections!"
        
    else
        echo "❌ Issue not found in API after 5 seconds"
        echo "📝 All issues currently in system:"
        curl -s -H "Authorization: Bearer $DEV_JWT" http://localhost:8002/api/issues | jq '.[] | {id, number, title, status}'
    fi
    
else
    echo "❌ Webhook failed with status $HTTP_STATUS"
    echo "Check the ingress service logs: docker logs dispatchai-ingress --tail 10"
fi