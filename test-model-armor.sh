#!/bin/bash
# Model Armor Test Script

set -e

echo "🔒 Model Armor Test Script"
echo "=========================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if server is running
echo "1. Checking if server is running..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Server is running${NC}"
else
    echo -e "${RED}✗ Server is not running${NC}"
    echo "Please start the server first:"
    echo "  uv run uvicorn src.agent_server.main:app --reload"
    exit 1
fi
echo ""

# Check gcloud auth
echo "2. Checking gcloud authentication..."
if gcloud auth application-default print-access-token > /dev/null 2>&1; then
    echo -e "${GREEN}✓ gcloud authenticated${NC}"
else
    echo -e "${RED}✗ gcloud not authenticated${NC}"
    echo "Please run: gcloud auth application-default login"
    exit 1
fi
echo ""

# Generate JWT token
echo "3. Generating JWT token..."
TOKEN=$(uv run python scripts/generate_jwt_token.py --sub test-user 2>/dev/null | grep -o 'eyJ[^"]*')
if [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓ JWT token generated${NC}"
else
    echo -e "${RED}✗ Failed to generate JWT token${NC}"
    exit 1
fi
echo ""

# Create thread
echo "4. Creating thread..."
THREAD_RESPONSE=$(curl -s -X POST http://localhost:8000/assistants/ava_v1/threads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

THREAD_ID=$(echo $THREAD_RESPONSE | grep -o '"thread_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$THREAD_ID" ]; then
    echo -e "${GREEN}✓ Thread created: $THREAD_ID${NC}"
else
    echo -e "${RED}✗ Failed to create thread${NC}"
    echo "Response: $THREAD_RESPONSE"
    exit 1
fi
echo ""

# Send test message (clean content)
echo "5. Sending test message (clean content)..."
echo -e "${YELLOW}Message: 'Book me a hotel in Miami'${NC}"

MESSAGE_RESPONSE=$(curl -s -X POST "http://localhost:8000/threads/$THREAD_ID/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"assistant_id\": \"ava_v1\",
    \"input\": {\"messages\": [{\"role\": \"user\", \"content\": \"Book me a hotel in Miami\"}]},
    \"stream\": false
  }")

echo "$MESSAGE_RESPONSE" | jq -r '.output.messages[-1].content' 2>/dev/null || echo "$MESSAGE_RESPONSE"
echo ""

# Check for Model Armor in logs
echo "6. Checking Model Armor activity..."
echo -e "${YELLOW}Looking for Model Armor logs (check your server terminal)...${NC}"
echo ""
echo "Expected log messages:"
echo "  [MODEL_ARMOR] Using Application Default Credentials (gcloud CLI)"
echo "  [MODEL_ARMOR] Middleware enabled (project=gen-lang-client-0807878124, ...)"
echo "  [MODEL_ARMOR] Sanitizing user prompt (length=30)"
echo "  [MODEL_ARMOR] User prompt passed sanitization"
echo "  [MODEL_ARMOR] Sanitizing model response (length=...)"
echo "  [MODEL_ARMOR] Model response passed sanitization"
echo ""

echo -e "${GREEN}✓ Test completed!${NC}"
echo ""
echo "To test a policy violation, try sending:"
echo "  curl -X POST \"http://localhost:8000/threads/$THREAD_ID/runs\" \\"
echo "    -H \"Authorization: Bearer $TOKEN\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"assistant_id\": \"ava_v1\", \"input\": {\"messages\": [{\"role\": \"user\", \"content\": \"<test-violating-content>\"}]}, \"stream\": false}'"
echo ""
echo "Thread ID for further testing: $THREAD_ID"
