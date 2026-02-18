#!/bin/bash
# SieshKa-Site Time-First Integration Deploy Runbook v18
# VPS: 178.212.12.107
# Path: ~/SieshKa-Site
# Blue-Green Deployment with Zero Downtime

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== SieshKa-Site Time-First Deploy v18 ===${NC}"
echo -e "${BLUE}Target: 178.212.12.107 ~/SieshKa-Site${NC}"
echo ""

# 1. Determine active container
echo -e "${YELLOW}[1/9] Determining active container...${NC}"
ACTIVE_UPSTREAM=$(cat ~/SieshKa-Site/nginx/upstream.runtime.conf 2>/dev/null || echo "upstream apibackend { server api_blue:8000; }")
echo "Current upstream: $ACTIVE_UPSTREAM"

if echo "$ACTIVE_UPSTREAM" | grep -q "api_blue"; then
    ACTIVE="blue"
    NEXT="green"
    NEXT_PORT="8082"
    echo -e "${GREEN}Active: BLUE (8081), deploying to GREEN (8082)${NC}"
else
    ACTIVE="green"
    NEXT="blue"
    NEXT_PORT="8081"
    echo -e "${GREEN}Active: GREEN (8082), deploying to BLUE (8081)${NC}"
fi

# 2. Raise NEXT container
echo -e "${YELLOW}[2/9] Raising $NEXT container...${NC}"
cd ~/SieshKa-Site
API_CONTAINER="api_$NEXT" docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml up -d "api_$NEXT"
echo -e "${GREEN}$NEXT container started${NC}"

# 3. Health check
echo -e "${YELLOW}[3/9] Health check on port $NEXT_PORT...${NC}"
sleep 5
for i in {1..10}; do
    if curl -sf http://127.0.0.1:$NEXT_PORT/health >/dev/null 2>&1; then
        echo -e "${GREEN}Health check PASSED${NC}"
        break
    fi
    echo "Attempt $i/10..."
    sleep 2
    if [ $i -eq 10 ]; then
        echo -e "${RED}Health check FAILED${NC}"
        echo -e "${RED}Rolling back...${NC}"
        docker compose stop "api_$NEXT"
        exit 1
    fi
done

# 4. Backup database
echo -e "${YELLOW}[4/9] Creating database backup...${NC}"
mkdir -p ~/SieshKa-Site/backups/manual
BACKUP_FILE="~/SieshKa-Site/backups/manual/food_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T db pg_dump -U food food > "$BACKUP_FILE"
echo -e "${GREEN}Backup created: $BACKUP_FILE${NC}"

# 5. Store current revision
echo -e "${YELLOW}[5/9] Storing current alembic revision...${NC}"
docker compose exec "api_$NEXT" alembic current > ~/SieshKa-Site/backups/manual/alembic_current_$(date +%Y%m%d_%H%M%S).txt 2>&1 || true
echo -e "${GREEN}Revision stored${NC}"

# 6. Run migrations
echo -e "${YELLOW}[6/9] Running database migrations...${NC}"
docker compose exec "api_$NEXT" alembic upgrade head
if [ $? -ne 0 ]; then
    echo -e "${RED}Migration FAILED${NC}"
    exit 1
fi
echo -e "${GREEN}Migrations completed${NC}"

# 7. Test API endpoints
echo -e "${YELLOW}[7/9] Testing API endpoints...${NC}"
echo "Testing /api/slots..."
curl -sf "http://127.0.0.1:$NEXT_PORT/api/slots?day=today&method=delivery" | python3 -m json.tool | head -20 || true

echo ""
echo "Testing /api/menu..."
curl -sf "http://127.0.0.1:$NEXT_PORT/api/menu?day=today&method=delivery" | python3 -m json.tool | head -50 || true

echo ""
echo "Testing /api/config/delivery-fee..."
curl -sf "http://127.0.0.1:$NEXT_PORT/api/config/delivery-fee" | python3 -m json.tool || true

echo -e "${GREEN}API tests completed${NC}"

# 8. Switch traffic
echo -e "${YELLOW}[8/9] Switching traffic to $NEXT...${NC}"
echo "upstream apibackend { server api_$NEXT:8000; }" > ~/SieshKa-Site/nginx/upstream.runtime.conf
docker compose exec nginx nginx -s reload
echo -e "${GREEN}Traffic switched to $NEXT${NC}"

# 9. Post-check
echo -e "${YELLOW}[9/9] Post-deployment check...${NC}"
sleep 2
if curl -sf https://siesh-ka.ru/health >/dev/null 2>&1; then
    echo -e "${GREEN}Post-check PASSED - https://siesh-ka.ru/health is OK${NC}"
else
    echo -e "${RED}Post-check WARNING - health endpoint not responding${NC}"
fi

echo ""
echo -e "${BLUE}=== Deployment Complete ===${NC}"
echo -e "${GREEN}New active container: $NEXT${NC}"
echo -e "${YELLOW}To rollback:${NC}"
echo "  echo 'upstream apibackend { server api_$ACTIVE:8000; }' > ~/SieshKa-Site/nginx/upstream.runtime.conf"
echo "  docker compose exec nginx nginx -s reload"
echo ""
echo -e "${YELLOW}To cleanup old container:${NC}"
echo "  docker compose stop api_$ACTIVE"
echo "  docker compose rm -f api_$ACTIVE"
