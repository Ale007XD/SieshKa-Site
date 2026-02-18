# SieshKa-Site VPS Deploy Runbook v18
## Time-First Integration

### Target
- **VPS**: 178.212.12.107
- **Path**: ~/SieshKa-Site
- **Domain**: siesh-ka.ru

### Quick Deploy (Copy-Paste)

```bash
# SSH to VPS
ssh user@178.212.12.107
cd ~/SieshKa-Site

# Run deploy script (single-use for Time-First integration)
./deploy-migration-2026-02-18-V2.sh
```

### What the Script Does

The `deploy-migration-2026-02-18-V2.sh` script performs the following steps:

1. **Git operations** - Fetches and resets to `origin/main` (discards local changes, keeps untracked files like .env)
2. **Database backup** - Creates backup before migrations (`backups/manual/backup_before_timefirst_v18_*.sql`)
3. **Docker deployment** - Rebuilds and restarts all containers
4. **Wait for database** - Ensures PostgreSQL is ready
5. **Apply migrations** - Runs all pending migrations in sequence:
   - `0003_add_availability_rules` - Creates availability_rules, cart_drafts, menu_configuration tables
   - `0004_add_delivery_fee` - Adds delivery_fee column to menu_configuration
   - `0005_seed_availability_rules` - Seeds default availability rules for all products
6. **Health check** - Verifies API is responding
7. **Test API endpoints** - Checks `/api/slots`, `/api/menu`, `/api/config/delivery-fee`

### Migration Sequence

```
0001_full_schema                    (base)
0002_add_category_parent_id         (parent_id for categories)
0003_add_availability_rules  ← NEW (Time-First tables)
0004_add_delivery_fee          ← NEW (delivery fee config)
0005_seed_availability_rules   ← NEW (seed data)
```

### Manual Verification Commands

```bash
# Check migration status
docker compose exec api alembic current
docker compose exec api alembic history

# Verify seeded data
docker compose exec db psql -U food -d food -c "SELECT COUNT(*) FROM availability_rules;"
docker compose exec db psql -U food -d food -c "SELECT * FROM menu_configuration;"

# Test API endpoints
curl "https://siesh-ka.ru/api/menu?day=today&method=delivery" | python3 -m json.tool
curl "https://siesh-ka.ru/api/slots?day=today&method=delivery" | python3 -m json.tool
curl "https://siesh-ka.ru/api/config/delivery-fee"
```

### Rollback (if needed)

```bash
# Rollback last migration
docker compose exec api alembic downgrade -1

# Or restore from backup
docker compose exec -T db psql -U food -d food < backups/manual/backup_before_timefirst_v18_*.sql
```

### Troubleshooting

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f db
docker compose logs -f nginx

# Restart specific container
docker compose restart api

# Check nginx config
docker compose exec nginx nginx -t

# Database console
docker compose exec db psql -U food -d food

# Redis check
docker compose exec redis redis-cli ping

# Manual migration (if script fails)
docker compose exec api alembic upgrade head
```

### Post-Deploy Verification Checklist

- [ ] https://siesh-ka.ru/health returns OK
- [ ] https://siesh-ka.ru/ shows menu with sticky bar
- [ ] Category filter works (click pills)
- [ ] Cart adds items correctly
- [ ] Offcanvas shows totals with delivery fee
- [ ] Recently deleted items visible in cart
- [ ] "/api/menu?day=today&method=delivery" returns products with badges
- [ ] "/api/slots?day=today&method=delivery" returns time slots
- [ ] Delivery fee is configured in admin panel

### Post-Deploy Configuration Required

1. **Set delivery fee in admin panel:**
   - Go to: https://siesh-ka.ru/admin
   - Navigate to: Настройки меню → Edit
   - Set field 'Стоимость доставки (₽)' to desired amount (e.g., 300)

2. **Verify Time-First integration:**
   - Open https://siesh-ka.ru/
   - Check sticky bar with day/method/slot selectors
   - Test category filter buttons
   - Add items to cart
   - Check offcanvas shows totals with delivery fee

### Files Changed

1. **alembic/versions/0003_add_availability_rules.py** - Time-First tables (already applied)
2. **alembic/versions/0004_add_delivery_fee.py** - Delivery fee column (already applied)
3. **alembic/versions/0005_seed_availability_rules.py** - Seed data for all products ⭐ NEW
4. **app/templates/index.html** - Time-First sticky bar + modal
5. **app/static/menu.js** - Time-First logic integration
6. **app/static/js/cart.js** - Upsell "add for later" feature
7. **deploy-migration-2026-02-18-V2.sh** - Deployment script ⭐ NEW
