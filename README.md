# SieshKa-Site v3.1.0-rc1 - Food Delivery Service 

Production-ready FastAPI-based food delivery service with PostgreSQL, Redis, SQLAdmin admin panel, Telegram notifications, Nginx reverse proxy with SSL/TLS, automated backups, **YooKassa payment schema**, and **checkout flow restoration**.

## 📋 Deployment Status

**Last Updated:** April 03, 2026

### ✅ Current Status: OPERATIONAL (85% Complete)

All core services running successfully:
- ✅ **API Service** - FastAPI backend (healthy, port 8002)
- ✅ **PostgreSQL** - Database running (healthy)
- ✅ **Redis** - Cache layer running (healthy)
- ✅ **Nginx** - SSL/TLS enabled, serving HTTPS
- ✅ **Admin Panel** - Accessible at `/admin`
- ✅ **Let's Encrypt SSL** - Certificates active

### 🔧 Recent Fixes Applied (2026-04-03)

1. **Checkout Flow Restoration** - Fixed `cash` regression after idempotency_key NOT NULL
2. **YooKassa Schema** - Added `PaymentMethod.yookassa_card`, nullable fields
3. **Database Migration** - `9c445de5fdf5` makes `orders.idempotency_key` nullable
4. **Schema Validation** - `OrderCreate.payment_method` supports `yookassa_card`
5. **Model Alignment** - `Order.idempotency_key` now `Mapped[str | None]`
6. **Smoke Tests** - `cash` → 200 OK, `yookassa_card` → 502 (creds pending)

### 🌐 Live Endpoints

- **Main Site**: [https://siesh-ka.ru](https://siesh-ka.ru)
- **Admin Panel**: [https://siesh-ka.ru/admin](https://siesh-ka.ru/admin)
- **Health Check**: [https://siesh-ka.ru/health](https://siesh-ka.ru/health)
- **Direct API**: `http://localhost:8002/health` (internal)
- **Metrics**: [https://siesh-ka.ru/metrics](https://siesh-ka.ru/metrics)

## 🚀 Quick Start

### Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.20+
- Apache2-utils (for `htpasswd`)

```bash
sudo apt update && sudo apt install apache2-utils -y
```

### 1. Clone/Extract

```bash
cd SieshKa-Site-v3.1-rc1
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env  # Add YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
```

**New Required Variables:**
