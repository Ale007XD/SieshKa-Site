#!/bin/bash
#
# One-time deployment script for delivery fee feature (2026-02-18)
# Usage: ./deploy-migration-2026-02-18.sh
#

set -e

echo "=== Sieshka Site Deployment - Delivery Fee Feature ==="

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "ERROR: docker-compose.yml not found. Run from project root."
    exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${YELLOW}Step 1: Git operations...${NC}"

# Reset any local changes to tracked files (keeps untracked like .env)
git checkout -- .

# Pull latest changes
git pull origin main

echo -e "${GREEN}✓ Git updated${NC}"

echo -e "${YELLOW}Step 2: Docker deployment...${NC}"

# Rebuild and restart
docker compose down
docker compose up -d --build

echo -e "${GREEN}✓ Containers started${NC}"

echo -e "${YELLOW}Step 3: Waiting for database...${NC}"
sleep 5

echo -e "${YELLOW}Step 4: Applying database migrations...${NC}"
docker compose exec -T api alembic upgrade head
echo -e "${GREEN}✓ Migrations applied successfully${NC}"

echo -e "${YELLOW}Step 5: Health check...${NC}"

# Wait a bit more for API to be fully ready
sleep 3

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
echo ""
echo -e "${BLUE}⚠ IMPORTANT: Next steps required!${NC}"
echo ""
echo "1. Set delivery fee in admin panel:"
echo "   https://siesh-ka.ru/admin"
echo ""
echo "2. Navigate to: Настройки меню → Edit"
echo ""
echo "3. Set field 'Стоимость доставки (₽)' to desired amount (e.g., 300)"
echo ""
echo -e "${GREEN}Site: https://siesh-ka.ru${NC}"
echo -e "${GREEN}Admin: https://siesh-ka.ru/admin${NC}"
echo -e "${GREEN}Health: https://siesh-ka.ru/health${NC}"
echo ""
echo "Useful commands:"
echo "  docker compose ps          # Check status"
echo "  docker compose logs -f     # View logs"
echo "  docker compose restart api # Restart API"
echo ""
