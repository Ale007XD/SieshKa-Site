#!/bin/bash
#
# SieshKa-Site Deployment Script
# Usage: ./deploy.sh [environment]
# Environment: development (default) | production
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENV=${1:-development}
PROJECT_NAME="sieshka"
COMPOSE_FILE="docker-compose.yml"

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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Environment setup
setup_environment() {
    log_info "Setting up environment ($ENV)..."
    
    if [ ! -f .env ]; then
        log_warning ".env file not found, creating from template..."
        cp .env.example .env
        log_warning "Please edit .env file with your configuration before continuing"
        exit 1
    fi
    
    # Create necessary directories
    mkdir -p backups logs
    touch backups/.gitkeep logs/.gitkeep
    
    # Set proper permissions
    chmod +x scripts/*.sh
    
    log_success "Environment setup complete"
}

# Build images
build_images() {
    log_info "Building Docker images..."
    
    docker compose -f $COMPOSE_FILE build --no-cache
    
    log_success "Images built successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    if [ "$ENV" == "production" ]; then
        docker compose -f $COMPOSE_FILE up -d
    else
        docker compose -f $COMPOSE_FILE up -d
    fi
    
    log_success "Services started"
}

# Wait for database
wait_for_db() {
    log_info "Waiting for database to be ready..."
    
    RETRIES=30
    until docker compose exec -T db pg_isready -U food -d food > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
        echo -n "."
        sleep 1
        RETRIES=$((RETRIES-1))
    done
    
    if [ $RETRIES -eq 0 ]; then
        log_error "Database failed to start"
        exit 1
    fi
    
    echo ""
    log_success "Database is ready"
}

# Run migrations
run_migrations() {
    log_info "Running database migrations..."
    
    docker compose run --rm api alembic upgrade head
    
    log_success "Migrations completed"
}

# Health check
health_check() {
    log_info "Performing health checks..."
    
    # Check API health
    RETRIES=10
    until curl -sf http://localhost:8000/health > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
        echo -n "."
        sleep 2
        RETRIES=$((RETRIES-1))
    done
    
    if [ $RETRIES -eq 0 ]; then
        log_error "API health check failed"
        docker compose logs api
        exit 1
    fi
    
    echo ""
    log_success "All health checks passed"
}

# Display status
show_status() {
    log_info "Deployment Status:"
    echo ""
    docker compose ps
    echo ""
    log_info "Application URLs:"
    if [ "$ENV" == "production" ]; then
        echo "  - Main Site: https://your-domain.com"
        echo "  - Admin Panel: https://your-domain.com/admin"
    else
        echo "  - Main Site: http://localhost"
        echo "  - Admin Panel: http://localhost/admin"
        echo "  - API Docs: http://localhost/docs"
    fi
    echo ""
    log_info "Useful commands:"
    echo "  - View logs: docker compose logs -f"
    echo "  - Shell: docker compose exec api /bin/sh"
    echo "  - Stop: docker compose down"
}

# Main deployment flow
main() {
    echo "========================================"
    echo "  SieshKa-Site Deployment Script"
    echo "  Environment: $ENV"
    echo "========================================"
    echo ""
    
    check_prerequisites
    setup_environment
    build_images
    start_services
    wait_for_db
    run_migrations
    health_check
    show_status
    
    log_success "Deployment completed successfully!"
}

# Run main function
main
