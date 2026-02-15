#!/bin/bash
#
# Blue/Green Deployment Script for Sieshka Food Delivery
# Usage: ./scripts/deploy-bluegreen.sh [command]
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_BASE="docker-compose.yml"
COMPOSE_BG="docker-compose.bluegreen.yml"
UPSTREAM_FILE="nginx/upstream.runtime.conf"
BACKUP_DIR="backups/manual"
ALEMBIC_FILE="$BACKUP_DIR/alembic_current.txt"

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "Script interrupted or failed"
    fi
}
trap cleanup EXIT

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

get_active_color() {
    if [ -f "$UPSTREAM_FILE" ]; then
        # Only match uncommented lines with the actual variable setting
        local active
        active=$(grep -v '^[[:space:]]*#' "$UPSTREAM_FILE" 2>/dev/null | grep 'set \$api_upstream' | grep -oP 'set \$api_upstream "\K[^"]+' | head -1)
        if [ -z "$active" ]; then
            echo "api_green"
        else
            echo "$active"
        fi
    else
        echo "api_green"
    fi
}

get_inactive_color() {
    local active=$1
    if [ "$active" == "api_blue" ]; then
        echo "api_green"
    else
        # Default: if green is active or unknown, deploy to blue
        echo "api_blue"
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found"
        exit 1
    fi
    
    # Check docker compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose not found"
        exit 1
    fi
    
    # Check env file
    if [ ! -f ".env" ]; then
        log_error ".env file not found"
        exit 1
    fi
    
    # Check compose files
    if [ ! -f "$COMPOSE_BASE" ]; then
        log_error "$COMPOSE_BASE not found"
        exit 1
    fi
    
    if [ ! -f "$COMPOSE_BG" ]; then
        log_error "$COMPOSE_BG not found"
        exit 1
    fi
    
    # Check nginx upstream file
    if [ ! -f "$UPSTREAM_FILE" ]; then
        log_warning "$UPSTREAM_FILE not found, creating with default"
        mkdir -p "$(dirname "$UPSTREAM_FILE")"
        echo 'set $api_upstream "api_green";' > "$UPSTREAM_FILE"
    fi
    
    log_success "Prerequisites OK"
}

create_backup() {
    log_info "Creating database backup..."
    
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/food_${timestamp}.sql"
    
    # Create backup
    if ! docker compose exec -T db pg_dump -U food -d food > "$backup_file"; then
        log_error "Backup failed"
        exit 1
    fi
    
    log_success "Backup created: $backup_file"
    echo "$backup_file" > "$BACKUP_DIR/latest_backup.txt"
    
    # Save current alembic revision from running container
    local active_color=$(get_active_color)
    log_info "Saving alembic revision from $active_color..."
    
    # Get revision ID only (first word of output)
    if docker compose ps "$active_color" | grep -q "healthy"; then
        docker compose exec "$active_color" alembic current 2>/dev/null | awk '{print $1}' > "$ALEMBIC_FILE" || {
            log_warning "Could not get alembic revision from $active_color"
            echo "head" > "$ALEMBIC_FILE"
        }
    else
        log_warning "Active color $active_color not running, cannot get alembic revision"
        echo "head" > "$ALEMBIC_FILE"
    fi
    
    log_success "Alembic revision saved to $ALEMBIC_FILE"
}

smoke_test() {
    local color=$1
    local port=$2
    
    log_info "Running smoke test on $color (port $port)..."
    
    # Wait for container to be healthy (with bluegreen profile)
    local retries=30
    local count=0
    
    while [ $count -lt $retries ]; do
        if docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" --profile bluegreen ps "$color" 2>/dev/null | grep -q "healthy"; then
            break
        fi
        sleep 2
        count=$((count + 1))
    done
    
    if [ $count -eq $retries ]; then
        log_error "Container $color did not become healthy"
        return 1
    fi
    
    # Test health endpoint via exposed port
    local health_url="http://127.0.0.1:$port/health"
    
    if curl -sf "$health_url" > /dev/null 2>&1; then
        log_success "Smoke test passed for $color"
        return 0
    else
        log_error "Smoke test failed for $color"
        return 1
    fi
}

switch_upstream() {
    local new_color=$1
    
    log_info "Switching upstream to $new_color..."
    
    # Update upstream file
    echo "set \$api_upstream \"$new_color\";" > "$UPSTREAM_FILE"
    
    # Reload nginx
    if ! docker compose exec nginx nginx -s reload; then
        log_error "Failed to reload nginx"
        return 1
    fi
    
    log_success "Upstream switched to $new_color"
}

deploy_color() {
    local target_color=$1
    local target_port
    
    if [ "$target_color" == "api_blue" ]; then
        target_port=8081
    else
        target_port=8082
    fi
    
    log_info "Deploying $target_color..."
    
    # Build and start the target color (with bluegreen profile)
    if ! docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" --profile bluegreen up -d --build "$target_color"; then
        log_error "Failed to build/start $target_color"
        return 1
    fi
    
    # Run smoke test
    if ! smoke_test "$target_color" "$target_port"; then
        log_error "Smoke test failed! Rolling back..."
        docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" --profile bluegreen stop "$target_color" || true
        return 1
    fi
    
    # Run migrations on the new color
    log_info "Running database migrations..."
    if ! docker compose exec "$target_color" alembic upgrade head; then
        log_error "Migration failed!"
        return 1
    fi
    
    log_success "$target_color deployed and migrated successfully"
    return 0
}

rollback() {
    log_warning "Initiating rollback..."
    
    local active_color=$(get_active_color)
    
    # Switch to the opposite color
    if [ "$active_color" == "api_blue" ]; then
        log_info "Switching to api_green..."
        switch_upstream "api_green"
    else
        log_info "Switching to api_blue..."
        switch_upstream "api_blue"
    fi
    
    log_success "Rollback completed - traffic switched"
    log_info "Note: Database migrations were NOT rolled back automatically"
    log_info "To rollback migrations, check $ALEMBIC_FILE and run:"
    log_info "  docker compose exec api alembic downgrade <revision>"
}

main() {
    log_info "=== Blue/Green Deployment Script ==="
    
    check_prerequisites
    
    # Determine colors
    local active_color=$(get_active_color)
    local inactive_color=$(get_inactive_color "$active_color")
    
    # Validate colors
    if [ "$inactive_color" != "api_blue" ] && [ "$inactive_color" != "api_green" ]; then
        log_error "Invalid target color: $inactive_color"
        exit 1
    fi
    
    log_info "Active color: $active_color"
    log_info "Inactive color (target): $inactive_color"
    log_info "Backup directory: $BACKUP_DIR"
    
    # Show deployment plan
    log_info "Deployment plan:"
    log_info "  - Building and starting: $inactive_color"
    log_info "  - Running smoke tests on port $([ "$inactive_color" == "api_blue" ] && echo "8081" || echo "8082")"
    log_info "  - Applying database migrations"
    log_info "  - Switching nginx upstream to $inactive_color"
    log_info "  - Stopping old color: $active_color"
    echo ""
    read -p "Continue with deployment? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warning "Deployment cancelled by user"
        exit 0
    fi
    
    # Create backup before deployment
    create_backup
    
    # Deploy to inactive color
    if ! deploy_color "$inactive_color"; then
        log_error "Deployment failed!"
        exit 1
    fi
    
    # Switch traffic
    if ! switch_upstream "$inactive_color"; then
        log_error "Failed to switch upstream! Rolling back..."
        rollback
        exit 1
    fi
    
    # Post-deployment check
    log_info "Running post-deployment check..."
    sleep 5
    
    if curl -sf https://siesh-ka.ru/health > /dev/null 2>&1; then
        log_success "Post-deployment check passed!"
    else
        log_error "Post-deployment check failed! Rolling back..."
        rollback
        exit 1
    fi
    
    # Stop old color after successful switch
    log_info "Stopping old color ($active_color)..."
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" --profile bluegreen stop "$active_color" || true
    
    log_success "=== Deployment Complete ==="
    log_info "Active color is now: $inactive_color"
    log_info "Previous color ($active_color) is stopped but available for rollback"
}

# Show help
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    echo "Blue/Green Deployment Script for Sieshka"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  (no args)    - Deploy to inactive color and switch traffic"
    echo "  status       - Show current deployment status"
    echo "  rollback     - Rollback to previous color"
    echo "  test         - Test script functions"
    echo ""
    echo "Examples:"
    echo "  $0                    # Deploy new version"
    echo "  $0 status            # Check status"
    echo "  $0 rollback          # Rollback deployment"
    exit 0
fi

# Handle commands
case "$1" in
    status)
        active=$(get_active_color)
        inactive=$(get_inactive_color "$active")
        echo "========================================"
        echo "Blue/Green Deployment Status"
        echo "========================================"
        echo "Active upstream: $active"
        echo "Inactive color:  $inactive"
        echo ""
        echo "Nginx upstream config:"
        cat "$UPSTREAM_FILE" 2>/dev/null | grep -v '^#' | head -5 || echo "  (not found)"
        echo ""
        echo "Alembic current revision:"
        cat "$ALEMBIC_FILE" 2>/dev/null || echo "  (not found)"
        echo ""
        echo "Latest backup:"
        cat "$BACKUP_DIR/latest_backup.txt" 2>/dev/null || echo "  (not found)"
        echo ""
        echo "Container status:"
        docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" --profile bluegreen ps 2>/dev/null || docker compose ps
        echo ""
        echo "Health checks:"
        echo -n "  Production (443): "
        curl -sf https://siesh-ka.ru/health > /dev/null 2>&1 && echo "OK" || echo "FAIL"
        echo -n "  Blue (8081):      "
        curl -sf http://127.0.0.1:8081/health > /dev/null 2>&1 && echo "OK" || echo "DOWN"
        echo -n "  Green (8082):     "
        curl -sf http://127.0.0.1:8082/health > /dev/null 2>&1 && echo "OK" || echo "DOWN"
        ;;
    rollback)
        rollback
        ;;
    test)
        echo "Testing script functions..."
        echo ""
        echo "1. Upstream file ($UPSTREAM_FILE) content:"
        if [ -f "$UPSTREAM_FILE" ]; then
            cat "$UPSTREAM_FILE"
        else
            echo "   File not found!"
        fi
        echo ""
        echo "2. get_active_color result: '$(get_active_color)'"
        echo "3. get_inactive_color(api_blue): '$(get_inactive_color "api_blue")'"
        echo "4. get_inactive_color(api_green): '$(get_inactive_color "api_green")'"
        echo "5. Environment check:"
        echo "   - .env exists: $([ -f .env ] && echo 'YES' || echo 'NO')"
        echo "   - $COMPOSE_BASE exists: $([ -f "$COMPOSE_BASE" ] && echo 'YES' || echo 'NO')"
        echo "   - $COMPOSE_BG exists: $([ -f "$COMPOSE_BG" ] && echo 'YES' || echo 'NO')"
        echo "   - Docker: $(docker --version 2>/dev/null | head -1 || echo 'NOT FOUND')"
        echo "   - Docker Compose: $(docker compose version 2>/dev/null | head -1 || echo 'NOT FOUND')"
        ;;
    *)
        main "$@"
        ;;
esac
