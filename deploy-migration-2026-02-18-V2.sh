#!/bin/bash
#
# One-time deployment script for Time-First Integration v18 (2026-02-18-V2)
# Includes migrations: 0003_add_availability_rules, 0004_add_delivery_fee, 0005_seed_availability_rules
# Usage: ./deploy-migration-2026-02-18-V2.sh
#

set -e

echo "=== Sieshka Site Deployment - Time-First Integration v18 ==="

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

echo -e "${YELLOW}Step 1: Git operations from origin/main...${NC}"

# Fetch latest changes from origin/main
git fetch origin main

# Reset to origin/main (discards local changes, keeps untracked like .env)
git reset --hard origin/main

echo -e "${GREEN}✓ Git reset to origin/main${NC}"

echo -e "${YELLOW}Step 2: Creating database backup...${NC}"

# Create backup directory if not exists
mkdir -p backups/manual

# Backup database before migrations
BACKUP_FILE="backups/manual/backup_before_timefirst_v18_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T db pg_dump -U food food > "$BACKUP_FILE" 2>/dev/null || echo -e "${YELLOW}⚠ Backup skipped (DB may not be running yet)${NC}"

if [ -f "$BACKUP_FILE" ]; then
    echo -e "${GREEN}✓ Database backup created: $BACKUP_FILE${NC}"
fi

echo -e "${YELLOW}Step 3: Docker deployment...${NC}"

# Rebuild and restart
docker compose down
docker compose up -d --build

echo -e "${GREEN}✓ Containers started${NC}"

echo -e "${YELLOW}Step 4: Waiting for database...${NC}"
sleep 5

# Wait for DB to be ready
for i in {1..10}; do
    if docker compose exec -T db pg_isready -U food > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Database is ready${NC}"
        break
    fi
    echo "Waiting for database... attempt $i/10"
    sleep 2
    if [ $i -eq 10 ]; then
        echo -e "${RED}✗ Database failed to start${NC}"
        exit 1
    fi
done

echo -e "${YELLOW}Step 5: Applying database migrations in sequence...${NC}"

# Check current revision
echo -e "${BLUE}Current revision:${NC}"
docker compose exec -T api alembic current || true

echo ""
echo -e "${YELLOW}Running migrations...${NC}"

# Apply all pending migrations (0003, 0004, 0005)
docker compose exec -T api alembic upgrade head
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Migration failed${NC}"
    echo -e "${YELLOW}You may need to run migrations manually:${NC}"
    echo "  docker compose exec api alembic upgrade head"
    exit 1
fi

echo -e "${GREEN}✓ Migrations applied successfully${NC}"

# Verify final revision
echo ""
echo -e "${BLUE}Final revision:${NC}"
docker compose exec -T api alembic current || true

echo -e "${YELLOW}Step 6: Health check...${NC}"

# Wait for API to be fully ready
sleep 3

# Check health
for i in {1..5}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is healthy${NC}"
        break
    fi
    echo "Health check attempt $i/5..."
    sleep 2
    if [ $i -eq 5 ]; then
        echo -e "${RED}✗ API health check failed${NC}"
        echo "Check logs: docker compose logs api --tail 20"
        exit 1
    fi
done

echo -e "${YELLOW}Step 7: Testing Time-First API endpoints...${NC}"

# Test /api/slots
echo -n "Testing /api/slots... "
if curl -sf "http://localhost:8000/api/slots?day=today&method=delivery" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARN (may need seed data)${NC}"
fi

# Test /api/menu
echo -n "Testing /api/menu... "
if curl -sf "http://localhost:8000/api/menu?day=today&method=delivery" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARN (may need seed data)${NC}"
fi

# Test /api/config/delivery-fee
echo -n "Testing /api/config/delivery-fee... "
if curl -sf "http://localhost:8000/api/config/delivery-fee" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARN${NC}"
fi

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo -e "${BLUE}⚠ IMPORTANT: Next steps required!${NC}"
echo ""
echo "1. Set delivery fee in admin panel:"
echo "   https://siesh-ka.ru/admin"
echo "   Navigate to: Настройки меню → Edit"
echo "   Set field 'Стоимость доставки (₽)' to desired amount (e.g., 300)"
echo ""
echo "2. Verify Time-First integration:"
echo "   - Open https://siesh-ka.ru/"
echo "   - Check sticky bar with day/method/slot selectors"
echo "   - Test category filter buttons"
echo "   - Add items to cart"
echo "   - Check offcanvas shows totals with delivery fee"
echo ""
echo -e "${GREEN}Site: https://siesh-ka.ru${NC}"
echo -e "${GREEN}Admin: https://siesh-ka.ru/admin${NC}"
echo -e "${GREEN}Health: https://siesh-ka.ru/health${NC}"
echo -e "${GREEN}API: https://siesh-ka.ru/api/menu?day=today&method=delivery${NC}"
echo ""
echo "Useful commands:"
echo "  docker compose ps                    # Check status"
echo "  docker compose logs -f api           # View API logs"
echo "  docker compose exec api alembic history   # View migration history"
echo "  docker compose exec db psql -U food -d food -c 'SELECT COUNT(*) FROM availability_rules;'  # Check seeded data"
echo ""
echo "Rollback (if needed):"
echo "  docker compose exec api alembic downgrade -1"
echo ""
