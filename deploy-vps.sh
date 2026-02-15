#!/bin/bash
#
# Simple deployment script for Sieshka Site
# Usage: ./deploy-vps.sh
#

set -e

echo "=== Sieshka Site Deployment ==="

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "ERROR: docker-compose.yml not found. Run from project root."
    exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Step 1: Preparing files...${NC}"

# Create runtime config from example if doesn't exist
if [ ! -f "nginx/upstream.runtime.conf" ]; then
    if [ -f "nginx/upstream.runtime.conf.example" ]; then
        cp nginx/upstream.runtime.conf.example nginx/upstream.runtime.conf
        echo -e "${GREEN}✓ Created nginx/upstream.runtime.conf from example${NC}"
    fi
fi

# Create deploy-bluegreen.sh from example if doesn't exist  
if [ ! -f "scripts/deploy-bluegreen.sh" ]; then
    if [ -f "scripts/deploy-bluegreen.sh.example" ]; then
        cp scripts/deploy-bluegreen.sh.example scripts/deploy-bluegreen.sh
        chmod +x scripts/deploy-bluegreen.sh
        echo -e "${GREEN}✓ Created scripts/deploy-bluegreen.sh from example${NC}"
    fi
fi

echo -e "${YELLOW}Step 2: Git operations...${NC}"

# Reset any local changes to tracked files (keeps untracked like .env)
git checkout -- .

# Pull latest changes
git pull origin main

echo -e "${GREEN}✓ Git updated${NC}"

echo -e "${YELLOW}Step 3: Docker deployment...${NC}"

# Rebuild and restart
docker compose down
docker compose up -d --build

# Wait for health check
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 5

# Check health
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo -e "${RED}✗ API health check failed${NC}"
    echo "Check logs: docker compose logs api --tail 20"
    exit 1
fi

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo "Site: https://siesh-ka.ru"
echo "Admin: https://siesh-ka.ru/admin"
echo "Health: https://siesh-ka.ru/health"
echo ""
echo "Useful commands:"
echo "  docker compose ps          # Check status"
echo "  docker compose logs -f     # View logs"
echo "  docker compose restart api # Restart API"
