#!/bin/bash

# Monitor script for PGS Call Translate
# This script monitors the health of the deployed application

APP_URL="$1"

if [ -z "$APP_URL" ]; then
    echo "Usage: $0 <app_url>"
    echo "Example: $0 https://your-app-name.azurewebsites.net"
    exit 1
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔍 Monitoring PGS Call Translate at: $APP_URL${NC}"
echo ""

# Function to check endpoint
check_endpoint() {
    local endpoint="$1"
    local name="$2"
    
    echo -n "Checking $name... "
    
    response=$(curl -s -w "%{http_code}" "$APP_URL$endpoint" -o /tmp/response.json)
    http_code="${response: -3}"
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✅ OK${NC}"
        if [ "$endpoint" = "/health" ]; then
            status=$(cat /tmp/response.json | jq -r '.status' 2>/dev/null || echo "unknown")
            echo "   Status: $status"
        elif [ "$endpoint" = "/status" ]; then
            sessions=$(cat /tmp/response.json | jq -r '.active_sessions' 2>/dev/null || echo "unknown")
            echo "   Active sessions: $sessions"
        fi
    else
        echo -e "${RED}❌ FAILED (HTTP $http_code)${NC}"
        return 1
    fi
}

# Check main endpoints
check_endpoint "/" "Main Interface"
check_endpoint "/health" "Health Check"
check_endpoint "/status" "Status"
check_endpoint "/docs" "API Documentation"

echo ""
echo -e "${GREEN}📊 Full Health Report:${NC}"

# Get detailed health info
health_response=$(curl -s "$APP_URL/health")
status_response=$(curl -s "$APP_URL/status")

if [ $? -eq 0 ]; then
    echo "Health: $(echo $health_response | jq -r '.status')"
    echo "Service: $(echo $health_response | jq -r '.service')"
    echo "Version: $(echo $health_response | jq -r '.version')"
    echo "Active Sessions: $(echo $status_response | jq -r '.active_sessions')"
    echo "Last Check: $(date)"
else
    echo -e "${RED}❌ Unable to retrieve health information${NC}"
fi

# Clean up
rm -f /tmp/response.json

echo ""
echo -e "${YELLOW}💡 Tip: Set up a cron job to run this script regularly for continuous monitoring${NC}"