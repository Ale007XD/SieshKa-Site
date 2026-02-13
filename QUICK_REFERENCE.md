# SieshKa-Site Quick Reference

## 🚀 One-Command Deployment

```bash
cd SieshKa-Site-final && ./deploy.sh
```

## 📋 Essential Commands

### Docker Compose
```bash
docker compose build          # Build images
docker compose up -d          # Start services
docker compose down           # Stop services
docker compose logs -f api    # View API logs
docker compose ps             # Check status
```

### Make (if available)
```bash
make build    # Build
docker compose up -d          # Start
make migrate  # Run migrations
make logs     # View logs
make backup   # Create backup
```

### Database
```bash
# Run migrations
docker compose run --rm api alembic upgrade head

# Create new migration
docker compose run --rm api alembic revision --autogenerate -m "description"

# Backup
docker compose exec -T db pg_dump -U food food | gzip > backup.sql.gz

# Restore
gunzip -c backup.sql.gz | docker compose exec -T db psql -U food -d food
```

## 🔧 Configuration

### Critical Env Vars (edit .env)
```bash
POSTGRES_PASSWORD=your_secure_password
BASE_URL=https://your-domain.com
TELEGRAM_BOT_TOKEN=your_bot_token
```

### File Locations
- Config: `.env` (create from `.env.example`)
- Docker: `docker-compose.yml`
- App: `app/main.py`
- Models: `app/models.py`
- Nginx: `nginx/default.conf`

## 🌐 Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Menu page |
| `/cart` | Shopping cart |
| `/checkout` | Order checkout |
| `/admin` | Admin panel (with auth) |
| `/api/orders` | Create order (POST) |
| `/health` | Health check |
| `/version` | App version |
| `/metrics` | Prometheus metrics |

## 🐛 Troubleshooting

### Services won't start
```bash
docker compose logs [service]
docker compose restart [service]
```

### Database issues
```bash
docker compose exec db pg_isready -U food
docker compose logs db
```

### Reset everything
```bash
docker compose down -v
docker compose up -d
```

## 🔒 Security Setup

### Create admin password
```bash
htpasswd -c nginx/.htpasswd admin
```

### SSL Certificates
```bash
# First time
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d your-domain.com

# Renew
docker compose restart nginx
```

## 📊 Monitoring

```bash
# Health
curl http://localhost/health

# Version
curl http://localhost/version

# Metrics
curl http://localhost/metrics
```

## 🧹 Cleanup

```bash
./cleanup.sh                    # Remove dev artifacts
docker system prune -f         # Clean Docker
```

## 📁 Project Files

```
SieshKa-Site-final/
├── README.md              # Full documentation
├── REPOSITORY_MANIFEST.json   # File inventory
├── ASSEMBLY_REPORT.md     # Assembly details
├── docker-compose.yml     # Services
├── Dockerfile            # API image
├── app/                  # Application code
├── config/               # Configuration
├── alembic/              # Migrations
├── nginx/                # Proxy config
└── scripts/              # Utilities
```

## 🆘 Emergency Contacts

- **Logs**: `docker compose logs -f`
- **Shell**: `docker compose exec api /bin/sh`
- **Database**: `docker compose exec db psql -U food`

---

**Quick Links**:
- [Full README](README.md)
- [Assembly Report](ASSEMBLY_REPORT.md)
- [File Manifest](REPOSITORY_MANIFEST.json)
