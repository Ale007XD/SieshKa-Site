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
    
    # Check apache2-utils for htpasswd
    if ! command -v htpasswd &> /dev/null; then
        log_warning "apache2-utils is not installed (needed for admin password)"
        log_info "Installing apache2-utils..."
        sudo apt update && sudo apt install apache2-utils -y || {
            log_error "Failed to install apache2-utils. Please install manually: sudo apt install apache2-utils"
            exit 1
        }
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
    
    # Check/create admin password file
    if [ ! -f nginx/.htpasswd ]; then
        log_warning "Admin password file not found (nginx/.htpasswd)"
        log_info "Creating admin password file..."
        read -sp "Enter admin password for /admin panel: " admin_pass
        echo
        htpasswd -cb nginx/.htpasswd admin "$admin_pass"
        log_success "Admin password file created"
    else
        log_info "Admin password file already exists"
    fi
    
    # Check SSL certificates for production
    if [ "$ENV" == "production" ]; then
        if [ ! -d "nginx/.htpasswd" ] && [ ! -f "nginx/.htpasswd" ]; then
            log_warning "SSL certificates may not be configured"
            log_info "To setup SSL, run: sudo certbot certonly --standalone -d your-domain.com"
        fi
    fi
    
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
    
    # Try Alembic migrations first
    if docker compose run --rm api alembic upgrade head 2>/dev/null; then
        log_success "Migrations completed"
    else
        log_warning "Alembic migrations failed, trying direct table creation..."
        docker compose exec api python -c "
from app.db import Base, engine
Base.metadata.create_all(bind=engine)
print('Tables created successfully!')
" && log_success "Tables created directly" || {
            log_error "Failed to create database tables"
            exit 1
        }
    fi
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
    
    # Check nginx (port 80 or 443)
    if curl -sf http://localhost > /dev/null 2>&1 || curl -sf -k https://localhost > /dev/null 2>&1; then
        log_success "Nginx is responding"
    else
        log_warning "Nginx check skipped (may need SSL setup)"
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
        echo "  - Health Check: https://your-domain.com/health"
    else
        echo "  - Main Site: http://localhost"
        echo "  - Admin Panel: http://localhost/admin"
        echo "  - Health Check: http://localhost/health"
        echo "  - API Docs: http://localhost/docs"
    fi
    echo ""
    log_info "Useful commands:"
    echo "  - View logs: docker compose logs -f"
    echo "  - Shell: docker compose exec api /bin/sh"
    echo "  - Stop: docker compose down"
    echo "  - Backup: docker compose exec -T db pg_dump -U food food | gzip > backup_$(date +%Y%m%d).sql.gz"
    echo ""
    log_info "Next steps:"
    echo "  1. Check the site: curl http://localhost/health"
    echo "  2. Setup SSL: sudo certbot certonly --standalone -d your-domain.com"
    echo "  3. Configure Telegram bot in .env (optional)"
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
