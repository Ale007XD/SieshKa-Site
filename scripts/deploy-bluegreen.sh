#!/bin/bash
#
# Blue/Green Deployment Script for Sieshka Food Delivery
# Usage: ./scripts/deploy-bluegreen.sh [blue|green]
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
        grep -oP 'set \$api_upstream "\K[^"]+' "$UPSTREAM_FILE" || echo "unknown"
    else
        echo "unknown"
    fi
}

get_inactive_color() {
    local active=$1
    if [ "$active" == "api_blue" ]; then
        echo "api_green"
    elif [ "$active" == "api_green" ]; then
        echo "api_blue"
    else
        echo "unknown"
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
    
    log_success "Prerequisites OK"
}

create_backup() {
    log_info "Creating database backup..."
    
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/food_${timestamp}.sql"
    
    # Get DB password from env
    local db_password=$(grep POSTGRES_PASSWORD .env | cut -d= -f2)
    
    # Create backup
    docker compose exec -T db pg_dump -U food -d food > "$backup_file"
    
    if [ $? -eq 0 ]; then
        log_success "Backup created: $backup_file"
        echo "$backup_file" > "$BACKUP_DIR/latest_backup.txt"
    else
        log_error "Backup failed"
        exit 1
    fi
    
    # Save current alembic revision
    local active_color=$(get_active_color)
    if [ "$active_color" != "unknown" ]; then
        docker compose exec "$active_color" alembic current > "$BACKUP_DIR/alembic_${timestamp}.txt" 2>/dev/null || true
    fi
}

smoke_test() {
    local color=$1
    local port=$2
    
    log_info "Running smoke test on $color (port $port)..."
    
    # Wait for container to be healthy
    local retries=30
    local count=0
    
    while [ $count -lt $retries ]; do
        if docker compose ps "$color" | grep -q "healthy"; then
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
    docker compose exec nginx nginx -s reload
    
    if [ $? -eq 0 ]; then
        log_success "Upstream switched to $new_color"
    else
        log_error "Failed to reload nginx"
        return 1
    fi
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
    
    # Build and start the target color
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" up -d --build "$target_color"
    
    # Run smoke test
    if ! smoke_test "$target_color" "$target_port"; then
        log_error "Smoke test failed! Rolling back..."
        docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" stop "$target_color"
        return 1
    fi
    
    # Run migrations on the new color
    log_info "Running database migrations..."
    docker compose exec "$target_color" alembic upgrade head
    
    if [ $? -ne 0 ]; then
        log_error "Migration failed!"
        return 1
    fi
    
    log_success "$target_color deployed successfully"
    return 0
}

rollback() {
    log_warning "Initiating rollback..."
    
    local active_color=$(get_active_color)
    local previous_revision=$(cat "$BACKUP_DIR/alembic_current.txt" 2>/dev/null || echo "")
    
    # Switch back to previous color if different
    if [ "$active_color" == "api_blue" ]; then
        switch_upstream "api_green"
    else
        switch_upstream "api_blue"
    fi
    
    # Rollback migrations if we have a previous revision
    if [ -n "$previous_revision" ]; then
        log_info "Rolling back migrations to: $previous_revision"
        docker compose exec "$active_color" alembic downgrade "$previous_revision"
    fi
    
    log_success "Rollback completed"
}

main() {
    log_info "=== Blue/Green Deployment Script ==="
    
    # Parse arguments
    local specified_color=$1
    
    check_prerequisites
    
    # Determine colors
    local active_color=$(get_active_color)
    local inactive_color=$(get_inactive_color "$active_color")
    
    log_info "Active color: $active_color"
    log_info "Inactive color (target): $inactive_color"
    
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
    docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_BG" stop "$active_color" || true
    
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
        echo "Active upstream: $active"
        docker compose ps
        ;;
    rollback)
        rollback
        ;;
    *)
        main "$@"
        ;;
esac
