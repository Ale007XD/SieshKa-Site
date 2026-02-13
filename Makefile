# Low Priority Fix: Makefile for common commands
.PHONY: help build up down logs shell migrate backup restore test lint format clean

# Default target
help:
	@echo "Available commands:"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View logs"
	@echo "  make shell      - Open shell in API container"
	@echo "  make migrate    - Run database migrations"
	@echo "  make backup     - Create database backup"
	@echo "  make restore    - Restore database from backup"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make format     - Format code"
	@echo "  make clean      - Clean up Docker resources"

# Build
build:
	docker-compose build

# Start services
up:
	docker-compose up -d

# Stop services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f api

# Open shell in API container
shell:
	docker-compose exec api /bin/sh

# Database migrations
migrate:
	docker-compose exec api alembic upgrade head

makemigrations:
	docker-compose exec api alembic revision --autogenerate -m "$(msg)"

# Backup
backup:
	@mkdir -p backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	docker-compose exec -T db pg_dump -U food food | gzip > backups/manual_$${TIMESTAMP}.sql.gz; \
	echo "Backup created: backups/manual_$${TIMESTAMP}.sql.gz"

# Restore (usage: make restore file=backups/backup_YYYYMMDD_HHMMSS.sql.gz)
restore:
	@if [ -z "$(file)" ]; then \
		echo "Usage: make restore file=backups/backup_YYYYMMDD_HHMMSS.sql.gz"; \
		exit 1; \
	fi
	gunzip -c $(file) | docker-compose exec -T db psql -U food -d food

# Tests
test:
	docker-compose exec api pytest -v

test-coverage:
	docker-compose exec api pytest --cov=app --cov-report=html

# Linting
lint:
	docker-compose exec api flake8 app
	docker-compose exec api mypy app

# Formatting
format:
	docker-compose exec api black app
	docker-compose exec api isort app

# Clean up
clean:
	docker-compose down -v
	docker system prune -f

# Development setup
dev-setup:
	cp .env.example .env
	mkdir -p backups logs
	touch backups/.gitkeep logs/.gitkeep
	@echo "Development environment setup complete!"
	@echo "Next steps:"
	@echo "  1. Edit .env file with your settings"
	@echo "  2. Run: make build"
	@echo "  3. Run: make up"
	@echo "  4. Run: make migrate"

# Production deployment
prod-deploy:
	@echo "Deploying to production..."
	docker-compose -f docker-compose.yml up -d
	docker-compose exec api alembic upgrade head
	@echo "Deployment complete!"

# Health check
health:
	@curl -s http://localhost:8000/health | jq .

# View metrics
metrics:
	@curl -s http://localhost:8000/metrics

# Check slot availability
slots:
	@curl -s "http://localhost:8000/api/slots/availability?target_date=$(date +%Y-%m-%d)" | jq .
