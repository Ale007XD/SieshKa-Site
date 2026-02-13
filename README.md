# SieshKa-Site v3.0.0-final - Food Delivery Service

Production-ready FastAPI-based food delivery service with PostgreSQL, Redis, SQLAdmin admin panel, Telegram notifications, Nginx reverse proxy with SSL/TLS, and automated backups.

## 📋 Deployment Status

**Last Updated:** February 13, 2026

### ✅ Current Status: OPERATIONAL

All services are running successfully:
- ✅ **API Service** - FastAPI backend (healthy)
- ✅ **PostgreSQL** - Database running (healthy)
- ✅ **Redis** - Cache layer running (healthy)
- ✅ **Nginx** - SSL/TLS enabled, serving HTTPS
- ✅ **Admin Panel** - Accessible at `/admin`
- ✅ **Let's Encrypt SSL** - Certificates active

### 🔧 Recent Fixes Applied (2026-02-13)

1. **PostgreSQL Permissions** - Removed `read_only: true` causing permission errors
2. **API Dockerfile** - Fixed path permissions for uvicorn (now using system paths)
3. **Backup Script** - Added `PGPASSWORD` export for pg_dump authentication
4. **Health Check** - Fixed SQLAlchemy 2.x compatibility (`text()` wrapper)
5. **Logging** - Fixed recursion error in request middleware
6. **SSL Certificates** - Obtained via Let's Encrypt certbot
7. **Database Tables** - Created via Alembic migrations

### 🌐 Live Endpoints

- **Main Site**: https://siesh-ka.ru
- **Admin Panel**: https://siesh-ka.ru/admin
- **Health Check**: https://siesh-ka.ru/health
- **Metrics**: https://siesh-ka.ru/metrics

## 🚀 Quick Start

### Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.20+
- Apache2-utils (for `htpasswd` command)
- Git (optional, for version control)

**Install htpasswd on Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install apache2-utils -y
```

### 1. Clone/Extract the Project

```bash
cd SieshKa-Site-final
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your production settings
nano .env  # or use your preferred editor
```

**Required environment variables:**
- `POSTGRES_PASSWORD` - Strong database password
- `BASE_URL` - Your domain (e.g., https://siesh-ka.ru)
- `TELEGRAM_BOT_TOKEN` - Bot token for notifications (optional but recommended)

### 3. Build and Start Services

```bash
# Build all Docker images
docker compose build

# Start services in detached mode
docker compose up -d

# Run database migrations
docker compose run --rm api alembic upgrade head

# Verify all services are running
docker compose ps
```

### 4. Access the Application

- **Main Site**: http://localhost (or your domain)
- **Admin Panel**: http://localhost/admin
- **Health Check**: http://localhost/health
- **Metrics**: http://localhost/metrics

### 5. Setup HTTPS (Production)

```bash
# Get SSL certificates (first time)
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d siesh-ka.ru

# Reload nginx to apply certificates
docker compose restart nginx
```

### 6. Setup Admin Panel Access

```bash
# Create password file for admin panel
htpasswd -cb nginx/.htpasswd admin your_secure_password

# Restart nginx to apply
docker compose restart nginx

# Access admin panel at: https://your-domain.ru/admin
# Login: admin
# Password: your_secure_password
```

## 📋 Available Commands

### Using Make (Recommended)

```bash
make help          # Show all available commands
make build         # Build Docker images
make up            # Start all services
make down          # Stop all services
make logs          # View logs
make shell         # Open shell in API container
make migrate       # Run database migrations
make backup        # Create database backup
make restore       # Restore database from backup
make clean         # Clean up Docker resources
```

### Using Docker Compose Directly

```bash
# Build
docker compose build

# Start
docker compose up -d

# Stop
docker compose down

# Logs
docker compose logs -f [service]

# Migrations
docker compose run --rm api alembic upgrade head

# Backup
docker compose exec -T db pg_dump -U food food | gzip > backup_$(date +%Y%m%d).sql.gz
```

## 🗂️ Project Structure

```
SieshKa-Site-final/
├── REPOSITORY_MANIFEST.json    # File inventory and metadata
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                  # Multi-stage API build
├── Makefile                    # Common commands
├── requirements.txt            # Python dependencies
├── alembic.ini                # Database migration config
├── .env.example               # Environment template
├── .dockerignore              # Docker build exclusions
├── .gitignore                 # Git exclusions
│
├── app/                       # FastAPI application
│   ├── main.py               # Main application
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # Pydantic schemas
│   ├── db.py                 # Database configuration
│   ├── admin.py              # SQLAdmin configuration
│   ├── telegram.py           # Telegram notifications
│   ├── templates/            # Jinja2 HTML templates
│   └── static/               # Static files (JS, CSS)
│
├── config/                    # Configuration modules
│   ├── settings.py           # Pydantic settings
│   └── constants.py          # Application constants
│
├── alembic/                   # Database migrations
│   ├── env.py                # Alembic environment
│   └── versions/             # Migration files
│
├── nginx/                     # Nginx configuration
│   └── default.conf          # Reverse proxy config
│
├── scripts/                   # Utility scripts
│   └── backup.sh             # Automated backup script
│
├── backups/                   # Database backups
└── logs/                      # Application logs
```

## 🔧 Configuration

### Environment Variables

See `.env.example` for all available options:

```env
# Database
POSTGRES_PASSWORD=change_me_in_production

# Application
BASE_URL=https://siesh-ka.ru
ENV=production
DEBUG=false

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TG_MANAGER_CHAT_ID=your_chat_id

# Admin Panel (SQLAdmin)
# Note: Basic Auth for /admin endpoint is configured via nginx/.htpasswd file
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_in_production

# Menu Schedule (Asia/Irkutsk timezone)
MORNING_START=07:00
MORNING_END=10:00
EVENING_START=15:00
EVENING_END=21:00

# Rate Limiting
RATE_LIMIT_PER_MINUTE=10
PHONE_RATE_LIMIT_PER_MINUTE=3
```

### Services

| Service | Image | Description | Port |
|---------|-------|-------------|------|
| db | postgres:16-alpine | PostgreSQL database | 5432 (internal) |
| redis | redis:7-alpine | Cache and session store | 6379 (internal) |
| api | Custom FastAPI | Main application | 8000 (internal) |
| nginx | nginx:alpine | Reverse proxy & SSL | 80, 443 |
| certbot | certbot/certbot | SSL certificate renewal | - |
| backup | postgres:16-alpine | Automated backups | - |

### Python Dependencies

Key libraries used in this project:

| Package | Version | Purpose |
|---------|---------|---------|
| FastAPI | 0.115.8 | Web framework |
| SQLAlchemy | 2.0.36 | ORM for PostgreSQL |
| psycopg | 3.2.3 | PostgreSQL driver |
| uvicorn | 0.30.6 | ASGI server |
| sqladmin | 0.20.1 | Admin panel |
| alembic | 1.13.2 | Database migrations |
| slowapi | 0.1.9 | Rate limiting |
| redis | 5.0.1 | Cache layer |
| httpx | 0.27.2 | HTTP client (Telegram) |
| phonenumbers | 9.0.23 | Phone validation |
| bleach | 6.1.0 | HTML sanitization |
| prometheus-client | 0.20.0 | Metrics |

See `requirements.txt` for complete list.

## 🔒 Security Features

- **Nginx Basic Auth** for `/admin` endpoint
- **Rate Limiting** per IP and phone number
- **Input Validation** with Pydantic schemas
- **SQL Injection Protection** via SQLAlchemy ORM
- **XSS Protection** with Jinja2 autoescape
- **Security Headers** (CSP, HSTS, X-Frame-Options)
- **Non-root Container** user for API service
- **Read-only Filesystem** for database container

## 📊 Monitoring

- **Health Checks**: `GET /health`
- **Prometheus Metrics**: `GET /metrics`
- **Application Version**: `GET /version`
- **System Diagnostics**: `GET /admin/diagnostics`
- **Structured Logging** with correlation IDs

## 💾 Backup & Recovery

### Automated Backups

Backups run automatically every 24 hours via the backup service.

### Manual Backup

```bash
make backup
# or
docker compose exec -T db pg_dump -U food food | gzip > backups/manual_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore from Backup

```bash
# Restore specific backup
gunzip -c backups/backup_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T db psql -U food -d food

# Or using make
make restore file=backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

## 🔄 Database Migrations

### Create New Migration

```bash
docker compose run --rm api alembic revision --autogenerate -m "description"
```

### Run Migrations

```bash
make migrate
# or
docker compose run --rm api alembic upgrade head
```

### Rollback Migration

```bash
docker compose run --rm api alembic downgrade -1
```

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check logs
docker compose logs -f [service]

# Restart service
docker compose restart [service]

# Check disk space
docker system df
```

### Database Connection Issues

```bash
# Check database health
docker compose exec db pg_isready -U food

# View database logs
docker compose logs db

# Reset database (WARNING: data loss)
docker compose down -v
docker compose up -d db
```

### Migration Failures

```bash
# Check migration status
docker compose run --rm api alembic current
docker compose run --rm api alembic history

# Mark migration as applied (if manually fixed)
docker compose run --rm api alembic stamp [revision_id]
```

### High Memory Usage

```bash
# View container stats
docker stats

# Prune unused resources
docker system prune -a
```

## 📝 API Documentation

When running in non-production mode:
- **Swagger UI**: http://localhost/docs
- **ReDoc**: http://localhost/redoc

### Key Endpoints

- `GET /` - Menu page
- `GET /cart` - Shopping cart
- `GET /checkout` - Order checkout
- `POST /api/orders` - Create order
- `GET /api/slots/availability` - Check delivery slots
- `GET /health` - Health check
- `GET /version` - Application version
- `GET /metrics` - Prometheus metrics

## 🧪 Testing

```bash
# Run tests
make test

# With coverage
make test-coverage
```

## 🚀 Production Deployment Checklist

- [ ] Change all default passwords in `.env`
- [ ] Configure Telegram bot token and chat IDs
- [ ] Set correct `BASE_URL` domain
- [ ] Obtain SSL certificates via Certbot
- [ ] Set up Nginx basic auth for admin panel
- [ ] Configure firewall rules (ports 80, 443)
- [ ] Set up log rotation
- [ ] Configure automated backups
- [ ] Test disaster recovery procedures
- [ ] Monitor resource usage

## 📚 Version History

- **v3.0.0-final** - Assembled release with documentation
- **v3.0.0** - Low priority fixes (optimization, config management)
- **v2.0.0** - Medium priority fixes (slots, caching, audit)
- **v1.0.0** - High priority fixes (backups, observability)

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Support

For issues and questions:
1. Check logs: `make logs`
2. Review this README
3. Check the Repository Manifest: `REPOSITORY_MANIFEST.json`
4. Consult the FastAPI and Docker documentation

---

**Built with ❤️ for Sieshka Restaurant**
