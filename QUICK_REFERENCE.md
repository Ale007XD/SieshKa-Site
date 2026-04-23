# SieshKa — Quick Reference (апрель 2026)

## Контейнеры и подключение

```bash
# Статус
docker compose ps

# Логи приложения
docker compose logs -f api_green

# Подключение к БД
docker compose exec db psql -U food -d food

# Алembic — применить миграции
docker compose exec api_green alembic upgrade head

# Алembic — новая миграция
docker compose exec api_green alembic revision --autogenerate -m "0021_описание"
```

## Переменные окружения — обязательные

```bash
DATABASE_URL=postgresql+psycopg://food:<pass>@db/food
REDIS_URL=redis://redis:6379/0

# YooKassa
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# MAX Messenger
MAX_BOT_TOKEN=
MAX_STAFF_CHAT_IDS=[123456789]
MAX_WEBHOOK_SECRET=
MAX_ALLOWED_USER_IDS=[123456789]
SITE_BASE_URL=https://siesh-ka.ru

# SMS
SMSC_API_KEY=
STAFF_PHONES=["+79990000000"]

# Таймзона (должна совпадать с MenuConfiguration.business_tz в БД)
TZ_NAME=Asia/Irkutsk
BUSINESS_TZ=Asia/Irkutsk
```

## Ключевые файлы

| Файл | Ответственность |
|---|---|
| `app/main.py` | Монолит 1880 строк, все роуты |
| `app/models.py` | SQLAlchemy-модели |
| `app/payments.py` | YooKassa create + webhook |
| `app/notifications.py` | Агрегатор MAX + SMS |
| `app/max_notify.py` | MAX Messenger API |
| `app/sms.py` | SMSC.ru API |
| `app/order_status.py` | FSM переходов |
| `app/timefirst_core.py` | Pure-функции слотов |
| `app/timefirst_api.py` | APIRouter /api/slots, /api/menu |
| `config/settings.py` | pydantic-settings |
| `app/db.py` | engine, SessionLocal |

## Статусы заказа

```
new → accepted → cooking → on_the_way → delivered
 └──────────────────────────────────────→ cancelled
```

## API — основные эндпоинты

```
POST /api/orders                    — создать заказ
POST /api/payments/webhook          — YooKassa webhook
POST /api/max/callback              — MAX Messenger webhook
GET  /api/slots?day=today&method=delivery
GET  /api/menu
GET  /health
GET  /metrics
```

## Smoke-тесты

```bash
# Здоровье
curl http://localhost:8002/health

# Слоты
curl "http://localhost:8002/api/slots?day=today&method=delivery"

# Меню (проверить snake_case полей)
curl http://localhost:8002/api/menu | python3 -m json.tool | grep -E "product_id|cta_type"
```

## Миграции — история

| Ревизия | Изменение |
|---|---|
| 0001 | Full schema |
| 0011 | allowed_methods |
| 0013 | order_number |
| 0014 | delivery_fee_rub |
| 0017 | client_max_uid |
| 0018 | max_message_ids, max_message_text |
| 0019 | delivery_zones |
| 0020 | delivery_mode: pickup/delivery |

## Технический долг — очередь

| Приоритет | Задача | Файл |
|---|---|---|
| P0 | Smoke-тест MAX клиентского бота | max_notify.py, main.py |
| P1 | Унифицировать таймзоны (убрать TZ_NAME из env) | main.py, settings.py |
| P2 | menu.js snake_case fix | static/menu.js |
| P3 | asyncio.to_thread для SessionLocal | main.py |
| P4 | Вынести orders.py роутер | main.py → routers/orders.py |
| P5 | Вынести admin_api.py роутер | main.py → routers/admin_api.py |
| P6 | Вынести system.py роутер | main.py → routers/system.py |
| P7 | Удалить мёртвый код (delivery_slots, get_slot_availability) | models.py, main.py |
