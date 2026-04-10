"""
Sieshka Food Delivery API v3.0.0

Low Priority Fixes:
- Compression middleware for responses
- Proper CORS configuration
- API documentation with OpenAPI tags
- Version endpoint
- Configuration management via pydantic-settings
"""

import sys
import uuid
import json
import logging
import signal
from datetime import datetime, time, date, timedelta, timezone
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text, func

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from cachetools import TTLCache

# Low Priority Fix: Import from config module
from config import settings
from config.constants import (
    VERSION,
    MAX_QTY_PER_ITEM,
    MAX_ITEMS_IN_CART,
    RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_REQUESTS_PER_WINDOW,
)

from .db import engine, SessionLocal
from .models import (
    Category,
    Product,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    DeliveryMode,
    MenuPeriod,
    DeliverySlot,
)
from .availability_models import MenuConfiguration

# [ШАГ 3] Заменён импорт из telegram на notifications-агрегатор
from .notifications import (
    notify_order_to_staff,
    get_failed_notifications_count,
    init_notifications,
    start_dlq_worker,
    stop_dlq_worker,
)
from .max_notify import (
    answer_max_callback,
    build_order_status_keyboard,
    send_max_start_reply,
    notify_client_status_update,
)
from .payments import (
    create_yookassa_payment,
    handle_webhook as handle_yookassa_webhook,
    YooKassaConfigError,
    YooKassaWebhookError,
)
from .admin import (
    setup_admin,
    update_order_status_endpoint,
    update_payment_status_endpoint,
    update_daypart_endpoint,
    update_method_endpoint,
)
from .schemas import (
    OrderCreate,
    HealthResponse,
    DeliverySlotsAvailability,
    DeliverySlotResponse,
)

# Time-First Menu System (v4.0)
from .timefirst_api import router as timefirst_router

# Юридические страницы
from .legal import router as legal_router

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore
    REDIS_AVAILABLE = False


# Structured logging with correlation IDs
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(record, "request_id", "N/A")
        return True


logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
REQUEST_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration")
ORDER_COUNT = Counter("orders_created_total", "Total orders created")
ORDER_FAILURE_COUNT = Counter("orders_failed_total", "Total order failures", ["reason"])

# Menu caching
menu_cache = TTLCache(maxsize=100, ttl=settings.MENU_CACHE_TTL)


# Graceful shutdown handler
def shutdown_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


# Security headers middleware
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' https://cdn.jsdelivr.net https://r2cdn.perplexity.ai; connect-src 'self' https://cdn.jsdelivr.net;"
    )
    return response


# Request/Response logging middleware
async def request_response_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = datetime.now()

    body = await request.body()
    logger.info(
        f"[{request_id}] Request {request.method} {request.url.path} - Body: {'***PII_MASKED***' if request.method in ('POST', 'PUT', 'PATCH') else (body[:1000].decode(errors='ignore') if body else 'empty')}"
    )

    try:
        response = await call_next(request)
        duration = (datetime.now() - start_time).total_seconds()

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()
        REQUEST_DURATION.observe(duration)

        logger.info(
            f"[{request_id}] Response {response.status_code} in {duration:.3f}s"
        )
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Request failed: {e}", exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Application v{VERSION} starting up...")

    # Initialize Redis connection
    if REDIS_AVAILABLE and aioredis is not None:
        try:
            app.state.redis = aioredis.from_url(
                settings.REDIS_URL, encoding="utf-8", decode_responses=True
            )
            logger.info("Redis connection established")
            # [ШАГ 3] Инициализируем агрегатор нотификаций и запускаем DLQ-воркер
            init_notifications(app.state.redis)
            start_dlq_worker()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            app.state.redis = None
            init_notifications(None)
    else:
        app.state.redis = None
        logger.warning("Redis not available (aioredis not installed)")
        init_notifications(None)

    yield

    # Cleanup
    # [ШАГ 3] Останавливаем DLQ-воркер перед закрытием Redis
    stop_dlq_worker()
    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()
        logger.info("Redis connection closed")

    logger.info("Application shutting down...")


# Low Priority Fix: Create FastAPI app with OpenAPI metadata
app = FastAPI(
    title=settings.APP_NAME,
    description="Food Delivery API for Sieshka restaurant",
    version=VERSION,
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
    openapi_url="/openapi.json" if settings.ENV != "production" else None,
    lifespan=lifespan,
)


# Low Priority Fix: Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version=VERSION,
        description="Food Delivery API for Sieshka restaurant",
        routes=app.routes,
    )

    # Add tags metadata
    openapi_schema["tags"] = [
        {
            "name": "Menu",
            "description": "Menu browsing and display",
        },
        {
            "name": "Orders",
            "description": "Order creation and management",
        },
        {
            "name": "Delivery",
            "description": "Delivery slots and availability",
        },
        {
            "name": "System",
            "description": "System health and monitoring",
        },
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Low Priority Fix: Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Low Priority Fix: Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add other middlewares
app.middleware("http")(security_headers_middleware)
app.middleware("http")(request_response_logging_middleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)


# Rate limiting with phone number tracking
class PhoneRateLimiter:
    def __init__(self):
        self.requests = {}
        self.window = RATE_LIMIT_WINDOW_SECONDS
        self.max_requests = settings.PHONE_RATE_LIMIT_PER_MINUTE
        self._cleanup_counter = 0
        self._cleanup_interval = RATE_LIMIT_REQUESTS_PER_WINDOW

    def _cleanup_old_entries(self):
        """Remove old entries to prevent memory leak"""
        now = datetime.now()
        keys_to_delete = []
        for key, timestamps in self.requests.items():
            # Keep only recent entries within the window
            self.requests[key] = [
                t for t in timestamps if now - t < timedelta(seconds=self.window)
            ]
            # Mark empty entries for deletion
            if not self.requests[key]:
                keys_to_delete.append(key)
        # Remove empty entries
        for key in keys_to_delete:
            del self.requests[key]

    def is_allowed(self, phone: str) -> bool:
        now = datetime.now()
        key = phone

        # Periodic cleanup to prevent memory leak
        self._cleanup_counter += 1
        if self._cleanup_counter >= self._cleanup_interval:
            self._cleanup_old_entries()
            self._cleanup_counter = 0

        if key not in self.requests:
            self.requests[key] = []

        self.requests[key] = [
            t for t in self.requests[key] if now - t < timedelta(seconds=self.window)
        ]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True


phone_rate_limiter = PhoneRateLimiter()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(
        f"Rate limit exceeded for {request.client.host if request.client else 'unknown'}"
    )
    ORDER_FAILURE_COUNT.labels(reason="rate_limit").inc()
    return JSONResponse(
        {"detail": "Too many requests, please try again later"}, status_code=429
    )


# Templates with autoescape enabled
from jinja2 import FileSystemLoader

templates = Jinja2Templates(directory="app/templates")
templates.env.autoescape = True
templates.env.loader = FileSystemLoader("app/templates")
templates.env.cache.clear() if hasattr(
    templates.env, "cache"
) and templates.env.cache else None

app.mount("/static", StaticFiles(directory="app/static"), name="static")

BASE_URL = settings.BASE_URL

DELIVERY_SLOTS = [
    "10:00-12:00",
    "12:00-14:00",
    "14:00-16:00",
    "16:00-18:00",
    "18:00-20:00",
]


def _parse_hhmm(s: str) -> time:
    hh, mm = s.strip().split(":")
    return time(int(hh), int(mm))


TZ_NAME = settings.TZ_NAME  # fallback


def get_local_tz() -> ZoneInfo:
    """
    Single source of truth for business timezone.
    Reads from MenuConfiguration in DB; falls back to settings.TZ_NAME
    if the DB is unavailable or the record doesn't exist yet.
    """
    try:
        with SessionLocal() as db:
            config = db.query(MenuConfiguration).first()
            if config and config.business_tz:
                return ZoneInfo(config.business_tz)
    except Exception:
        pass
    return ZoneInfo(TZ_NAME)

MORNING_START = _parse_hhmm(settings.MORNING_START)
MORNING_END = _parse_hhmm(settings.MORNING_END)
EVENING_MENU_START = _parse_hhmm(
    settings.EVENING_MENU_START
)  # Время показа вечернего меню
EVENING_START = _parse_hhmm(
    settings.EVENING_START
)  # Время начала доставки вечернего меню
EVENING_END = _parse_hhmm(settings.EVENING_END)

ASAP_TEXT = settings.ASAP_TEXT

MAX_QTY = MAX_QTY_PER_ITEM
MAX_ITEMS = MAX_ITEMS_IN_CART

# Setup admin
setup_admin(app, engine)

# Include time-first menu API
app.include_router(timefirst_router)

# Юридические страницы
app.include_router(legal_router)

import ipaddress

# YooKassa IP allowlist (https://yookassa.ru/developers/using-api/webhooks)
_YOOKASSA_NETWORKS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.156.128/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
]


def _is_yookassa_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _YOOKASSA_NETWORKS)
    except ValueError:
        return False


# Admin API endpoint for order status updates
@app.post("/admin/api/orders/update-status")
async def admin_update_order_status(request: Request):
    """Proxy to admin status update endpoint"""
    return await update_order_status_endpoint(request)


# Admin API endpoint for order payment status updates
@app.post("/api/admin/orders/update-payment")
async def admin_update_payment_status(request: Request):
    """Proxy to admin payment status update endpoint"""
    return await update_payment_status_endpoint(request)


# Admin API endpoint for product active status toggle
@app.post("/api/admin/products/toggle-active")
async def admin_toggle_product_active(request: Request):
    """Proxy to product active status toggle endpoint"""
    from .admin import toggle_product_active_endpoint

    return await toggle_product_active_endpoint(request)


# Admin API endpoint for availability rule daypart updates
@app.post("/api/admin/availability-rules/update-daypart")
async def admin_update_daypart(request: Request):
    """Proxy to availability rule daypart update endpoint"""
    return await update_daypart_endpoint(request)


# Admin API endpoint for availability rule method updates
@app.post("/api/admin/availability-rules/update-method")
async def admin_update_method(request: Request):
    """Proxy to availability rule method update endpoint"""
    return await update_method_endpoint(request)


def _parse_csv_form(form_data: Any) -> dict:
    """Extract form data for CSV import"""
    uploaded_file = form_data.get("csv_file")
    default_category_id_raw = form_data.get("default_category_id")
    skip_errors = form_data.get("skip_errors") == "on"

    default_category_id: int | None = None
    if default_category_id_raw and isinstance(default_category_id_raw, str):
        try:
            default_category_id = int(default_category_id_raw)
        except ValueError:
            pass

    return {
        "uploaded_file": uploaded_file,
        "default_category_id": default_category_id,
        "skip_errors": skip_errors,
    }


async def _decode_csv_file(uploaded_file: Any) -> tuple[str | None, str | None]:
    """Read and decode CSV file content. Returns (csv_text, error_message)"""
    from fastapi import UploadFile

    if not uploaded_file or not isinstance(uploaded_file, UploadFile):
        return None, "Файл не загружен"

    content = await uploaded_file.read()
    logger.info(f"CSV file size: {len(content)}, first 50 bytes: {content[:50]}")

    for encoding in ["utf-8-sig", "utf-8", "cp1251", "latin1"]:
        try:
            csv_text = content.decode(encoding)
            return csv_text, None
        except:
            continue

    return None, "Не удалось декодировать файл"


def _parse_csv_content(csv_text: str) -> tuple[Any, str | None]:
    """Parse CSV text into reader. Returns (csv_reader, error_message)"""
    import csv
    import io

    first_line = csv_text.split("\n")[0]
    delimiter = ";" if ";" in first_line and "," not in first_line else ","
    logger.info(f"Detected delimiter: '{delimiter}'")

    csv_reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

    fieldnames = csv_reader.fieldnames or []
    fieldnames_lower = [f.lower().strip() for f in fieldnames]

    if not fieldnames:
        return None, "Не удалось прочитать CSV файл"

    if "name" not in fieldnames_lower:
        return None, f"CSV файл должен содержать колонку 'Name'. Найдены: {fieldnames}"

    return csv_reader, None


def _process_single_row(
    row: dict, row_num: int, db: Any, default_cat: Any, skip_errors: bool
) -> tuple[dict | None, str | None]:
    """Process a single CSV row. Returns (skipped_info, error_message)"""
    row_lower = {k.lower().strip(): (v.strip() if v else None) for k, v in row.items()}

    name_raw = row_lower.get("name", "")
    name = name_raw.strip() if name_raw else ""
    if not name:
        if skip_errors:
            return {"name": "(пусто)", "reason": "отсутствует Name"}, None
        return None, f"Строка {row_num}: отсутствует Name"

    category_id = default_cat.id if default_cat else None
    category_raw = row_lower.get("category", "")
    category_value = category_raw.strip() if category_raw else ""

    if category_value:
        if category_value.isdigit():
            category_id = int(category_value)
        else:
            cat = (
                db.query(Category)
                .filter(func.lower(Category.name) == category_value.lower())
                .first()
            )
            if cat:
                category_id = cat.id

    if not category_id:
        if skip_errors:
            return {
                "name": name,
                "reason": f"категория '{category_value}' не найдена",
            }, None
        return None, f"Строка {row_num}: категория не найдена"

    existing = db.query(Product).filter(Product.name == name).first()
    if existing:
        return {"name": name, "reason": "товар уже существует"}, None

    desc_raw = row_lower.get("description", "")
    description = desc_raw.strip() if desc_raw else ""
    price_raw = row_lower.get("price rub", "")
    price_str = price_raw.strip() if price_raw else ""
    price = int(price_str) if price_str and price_str.isdigit() else 0
    photo_raw = row_lower.get("photo url", "")
    photo_url = photo_raw.strip() if photo_raw else ""

    product = Product(
        name=name,
        category_id=category_id,
        description=description,
        price_rub=price,
        photo_url=photo_url,
        is_active=True,
    )

    db.add(product)
    return None, None


# Admin API endpoint for CSV product import
@app.post("/api/admin/products/import-csv")
async def import_products_csv(request: Request):
    """API endpoint for CSV product import - refactored"""
    from .db import SessionLocal
    from .models import Category

    try:
        form_data = await request.form()
        parsed = _parse_csv_form(form_data)

        csv_text, error = await _decode_csv_file(parsed["uploaded_file"])
        if error:
            return {"success": False, "error": error}

        csv_reader, error = _parse_csv_content(csv_text)  # type: ignore[arg-type]
        if error:
            return {"success": False, "error": error}

        results = {"created": 0, "errors": [], "skipped": [], "skipped_count": 0}

        with SessionLocal() as db:
            default_cat = None
            if parsed["default_category_id"]:
                default_cat = (
                    db.query(Category)
                    .filter(Category.id == parsed["default_category_id"])
                    .first()
                )

            for row_num, row in enumerate(csv_reader, start=2):  # type: ignore[union-attr]
                try:
                    skipped, error = _process_single_row(
                        row, row_num, db, default_cat, parsed["skip_errors"]
                    )

                    if skipped:
                        results["skipped"].append(skipped)
                        continue

                    if error:
                        if parsed["skip_errors"]:
                            results["skipped"].append(
                                {"name": "(error)", "reason": error}
                            )
                        else:
                            results["errors"].append(error)
                        continue

                    results["created"] += 1

                except Exception as e:
                    if parsed["skip_errors"]:
                        results["skipped"].append(
                            {"name": "(unknown)", "reason": f"ошибка: {str(e)[:50]}"}
                        )
                    else:
                        results["errors"].append(f"Строка {row_num}: {str(e)}")

            db.commit()
            menu_cache.clear()

        results["skipped_count"] = len(results["skipped"])
        return {"success": True, "results": results}

    except Exception as e:
        return {"success": False, "error": str(e)}


def normalize_ru_phone(phone_raw: str) -> str:
    try:
        num = phonenumbers.parse(phone_raw, None)
    except NumberParseException:
        raise HTTPException(
            400, "Телефон не распознан, используйте формат +7XXXXXXXXXX"
        )

    if num.country_code != 7:
        raise HTTPException(400, "Нужен телефон РФ (+7)")

    if not phonenumbers.is_valid_number(num):
        raise HTTPException(400, "Телефон недействителен")

    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def get_current_menu_period(now: datetime) -> str | None:
    """Определяет какое меню показывать (morning/evening)
    В ночное время (после EVENING_END до MORNING_START) возвращает 'morning' для предзаказа
    """
    t = now.time()
    if MORNING_START <= t <= MORNING_END:
        return "morning"
    if EVENING_MENU_START <= t <= EVENING_END:
        return "evening"
    if EVENING_END < t or t < MORNING_START:
        return "morning"
    return None


def is_preorder_mode(now: datetime) -> bool:
    """Проверяет, находимся ли в режиме предзаказа (ночное время)"""
    t = now.time()
    return EVENING_END < t or t < MORNING_START


def get_preorder_info(now: datetime) -> dict:
    """Возвращает информацию о предзаказе для ночного времени"""
    if not is_preorder_mode(now):
        return {"is_preorder": False}

    today = now.date()
    morning_start_dt = datetime.combine(today, MORNING_START)
    if now.time() > EVENING_END:
        morning_start_dt = datetime.combine(today + timedelta(days=1), MORNING_START)

    if now.tzinfo:
        morning_start_dt = morning_start_dt.replace(tzinfo=now.tzinfo)

    delta = morning_start_dt - now
    total_minutes = int(delta.total_seconds() / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours > 0:
        time_until = f"{hours} ч {minutes} мин"
    else:
        time_until = f"{minutes} мин"

    return {
        "is_preorder": True,
        "opens_at": MORNING_START.strftime("%H:%M"),
        "time_until": time_until,
        "hours": hours,
        "minutes": minutes,
    }


def get_current_period_label(now: datetime) -> str | None:
    """Определяет доступность доставки (morning/evening) - для обратной совместимости"""
    t = now.time()
    if MORNING_START <= t <= MORNING_END:
        return "morning"
    if EVENING_START <= t <= EVENING_END:
        return "evening"
    return None


def is_menu_available(now: datetime) -> bool:
    return get_current_menu_period(now) is not None


def is_delivery_available(now: datetime) -> bool:
    """Проверяет доступность доставки в текущий момент"""
    t = now.time()
    return (MORNING_START <= t <= MORNING_END) or (EVENING_START <= t <= EVENING_END)


def check_slot_availability(db, slot_time: str, delivery_date: date) -> bool:
    """
    Validate slot_time (HH:MM) against the timefirst virtual slot grid
    and check that the per-slot order cap has not been reached.
    """
    from datetime import datetime as _dt
    from app.timefirst_core import get_slots, DeliveryMethod as _DM
    from app.availability_models import MenuConfiguration
    import datetime as _datetime

    config = db.query(MenuConfiguration).first()
    if not config:
        return False

    tz = ZoneInfo(config.business_tz)
    now = _dt.now(tz)
    today = now.date()

    if delivery_date < today:
        return False

    target_day = "today" if delivery_date == today else "tomorrow"

    slots, _err = get_slots(
        target_day=target_day,
        method=_DM("delivery"),
        now=now,
        interval_minutes=config.slot_interval_minutes,
        base_buffer_minutes=config.base_buffer_minutes,
        tomorrow_cutoff=config.tomorrow_order_cutoff
        if config.enable_tomorrow_orders
        else _datetime.time(0, 0),
    )

    available_times = {s.time.strftime("%H:%M") for s in slots if s.available}
    if slot_time not in available_times:
        return False

    # Check per-slot order cap
    current_orders = (
        db.query(Order)
        .filter(
            Order.delivery_slot == slot_time,
            Order.delivery_date == delivery_date,
            Order.status.notin_(["cancelled"]),
        )
        .count()
    )
    return current_orders < config.max_orders_per_slot


def get_slot_availability(db, target_date: date) -> list:
    slots = db.query(DeliverySlot).filter(DeliverySlot.is_active == True).all()
    availability = []

    for slot in slots:
        current_orders = (
            db.query(Order)
            .filter(
                Order.delivery_slot == slot.slot_time,
                Order.delivery_date == target_date,
                Order.status.notin_(["cancelled"]),
            )
            .count()
        )

        availability.append(
            {
                "slot_time": slot.slot_time,
                "max_orders": slot.max_orders,
                "current_orders": current_orders,
                "available": current_orders < slot.max_orders,
            }
        )

    return availability


# Low Priority Fix: Version endpoint
@app.get("/version", tags=["System"])
async def get_version():
    """Get application version information"""
    return {
        "version": VERSION,
        "app_name": settings.APP_NAME,
        "environment": settings.ENV,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health", tags=["System"], response_model=HealthResponse)
async def health():
    """Health check endpoint for monitoring"""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

        # Check Redis
        redis_status = "not_configured"
        if hasattr(app.state, "redis") and app.state.redis:
            try:
                await app.state.redis.ping()
                redis_status = "connected"
            except Exception as e:
                redis_status = f"error: {str(e)}"

        return HealthResponse(
            status="ok",
            version=VERSION,
            database="connected",
            redis=redis_status,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            {"status": "error", "detail": "Database connection failed"}, status_code=503
        )


@app.get("/admin/diagnostics", tags=["System"])
async def diagnostics():
    """System diagnostics for administrators"""
    return {
        "version": VERSION,
        # [ШАГ 3] get_failed_notifications_count теперь async (читает dlq:max из Redis)
        "failed_notifications": await get_failed_notifications_count(),
        "time": datetime.now(timezone.utc).isoformat(),
        "menu_available": is_menu_available(datetime.now(get_local_tz())),
    }


@app.get(
    "/api/slots/availability",
    response_model=DeliverySlotsAvailability,
    tags=["Delivery"],
)
async def get_slots_availability(target_date: date = Query(default_factory=date.today)):
    """Get delivery slot availability for a specific date"""
    if target_date < date.today():
        raise HTTPException(400, "Cannot check availability for past dates")

    with SessionLocal() as db:
        slots = get_slot_availability(db, target_date)
        return DeliverySlotsAvailability(
            date=target_date, slots=[DeliverySlotResponse(**slot) for slot in slots]
        )


@app.get("/api/config/delivery-fee", tags=["Config"])
async def get_delivery_fee():
    """Get current delivery fee from configuration"""
    with SessionLocal() as db:
        config = db.query(MenuConfiguration).first()
        if config:
            return {"delivery_fee": config.delivery_fee}
        return {"delivery_fee": 0}


@app.get("/", response_class=HTMLResponse, tags=["Menu"])
async def index(request: Request, preview_period: str = Query(None)):
    """Main menu page"""
    now = datetime.now(get_local_tz())

    if preview_period in ("morning", "evening"):
        current_period = preview_period
    else:
        current_period = get_current_menu_period(now)

    if current_period is None and not preview_period:
        return templates.TemplateResponse(
            "closed.html",
            {
                "request": request,
                "morning_start": MORNING_START.strftime("%H:%M"),
                "morning_end": MORNING_END.strftime("%H:%M"),
                "evening_start": EVENING_START.strftime("%H:%M"),
                "evening_end": EVENING_END.strftime("%H:%M"),
            },
        )

    cache_key = f"menu_{current_period}_{preview_period}"
    cached_data = menu_cache.get(cache_key)

    if cached_data:
        logger.debug(f"Serving menu from cache: {cache_key}")
        return templates.TemplateResponse(
            "index.html", {"request": request, **cached_data}
        )

    with SessionLocal() as db:
        # Load global configuration
        config = db.query(MenuConfiguration).first()
        allowed_methods = config.allowed_methods if config else "both"

        # Load only root categories (no parent) and their subcategories
        root_cats = (
            db.query(Category)
            .filter(Category.is_active == True, Category.parent_id == None)
            .order_by(Category.sort)
            .all()
        )

        # Load all active products in ONE query and group by category_id (fix N+1)
        all_products = db.query(Product).filter(Product.is_active == True).all()
        products_by_category = {}
        for p in all_products:
            if p.category_id not in products_by_category:
                products_by_category[p.category_id] = []
            products_by_category[p.category_id].append(p)

        # Build hierarchical structure
        categories_data = []

        for root_cat in root_cats:
            cat_data = {"category": root_cat, "subcategories": [], "products": []}

            # Get products directly in this category from preloaded dict
            direct_products = products_by_category.get(root_cat.id, [])

            for p in direct_products:
                period = p.menu_period_override or root_cat.menu_period
                if period == MenuPeriod.both or period.value == current_period:
                    cat_data["products"].append(p)

            # Get subcategories and their products
            for subcat in root_cat.children:
                if not subcat.is_active:
                    continue

                subcat_data = {"category": subcat, "products": []}

                # Get products for subcategory from preloaded dict
                subcat_products = products_by_category.get(subcat.id, [])

                for p in subcat_products:
                    period = p.menu_period_override or subcat.menu_period
                    if period == MenuPeriod.both or period.value == current_period:
                        subcat_data["products"].append(p)

                if subcat_data["products"]:
                    cat_data["subcategories"].append(subcat_data)

            # Only add category if it has products or subcategories with products
            if cat_data["products"] or cat_data["subcategories"]:
                categories_data.append(cat_data)

        preorder_info = get_preorder_info(now)

        data = {
            "categories_data": categories_data,
            "current_period_label": current_period,
            "preview_period": preview_period,
            "preorder_info": preorder_info,
            "allowed_methods": allowed_methods,
        }

        if not preorder_info["is_preorder"]:
            menu_cache[cache_key] = data

        return templates.TemplateResponse("index.html", {"request": request, **data})


@app.get("/cart", response_class=HTMLResponse, tags=["Menu"])
async def cart_page(request: Request):
    """Shopping cart page"""
    return templates.TemplateResponse("cart.html", {"request": request})


@app.get("/checkout", response_class=HTMLResponse, tags=["Orders"])
async def checkout_page(request: Request):
    """Checkout page"""
    now = datetime.now(get_local_tz())
    current_menu_period = get_current_menu_period(now)
    current_delivery_period = get_current_period_label(now)
    preorder_info = get_preorder_info(now)

    if current_menu_period is None and not preorder_info["is_preorder"]:
        return templates.TemplateResponse(
            "closed.html",
            {
                "request": request,
                "morning_start": MORNING_START.strftime("%H:%M"),
                "morning_end": MORNING_END.strftime("%H:%M"),
                "evening_start": EVENING_START.strftime("%H:%M"),
                "evening_end": EVENING_END.strftime("%H:%M"),
            },
        )

    show_delivery_notice = (
        current_menu_period == "evening" and current_delivery_period is None
    )

    return templates.TemplateResponse(
        "checkout.html",
        {
            "request": request,
            "delivery_slots": DELIVERY_SLOTS,
            "current_menu_period": current_menu_period,
            "show_delivery_notice": show_delivery_notice,
            "evening_delivery_start": EVENING_START.strftime("%H:%M"),
            "preorder_info": preorder_info,
            "morning_start": MORNING_START.strftime("%H:%M"),
        },
    )


@app.post("/api/orders", tags=["Orders"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_order(request: Request, payload: OrderCreate):
    """Create a new order with idempotency protection and slot validation"""
    logger.info(
        f"Creating order from {request.client.host if request.client else 'unknown'}"
    )

    try:
        phone_e164 = normalize_ru_phone(payload.phone)
    except HTTPException:
        ORDER_FAILURE_COUNT.labels(reason="invalid_phone").inc()
        raise

    if not phone_rate_limiter.is_allowed(phone_e164):
        logger.warning(f"Phone rate limit exceeded for {phone_e164}")
        ORDER_FAILURE_COUNT.labels(reason="phone_rate_limit").inc()
        raise HTTPException(
            429, "Слишком много заказов с этого номера. Попробуйте позже."
        )

    with SessionLocal.begin() as db:
        try:
            existing = (
                db.query(Order)
                .filter(Order.idempotency_key == payload.idempotency_key)
                .first()
            )

            if existing:
                logger.info(
                    f"Returning existing order {existing.id} for idempotency key"
                )
                return {"ok": True, "order_id": existing.id, "existing": True}

            if payload.delivery_mode == "slot":
                if not payload.delivery_slot or not payload.delivery_date:
                    ORDER_FAILURE_COUNT.labels(reason="missing_slot_data").inc()
                    raise HTTPException(400, "Не указан слот или дата доставки")
                if not check_slot_availability(
                    db, payload.delivery_slot, payload.delivery_date
                ):
                    ORDER_FAILURE_COUNT.labels(reason="slot_unavailable").inc()
                    raise HTTPException(
                        400, "Выбранный слот доставки заполнен. Выберите другой."
                    )

            product_ids = [i.product_id for i in payload.items]
            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids), Product.is_active == True)
                .all()
            )

            if len(products) != len(product_ids):
                logger.warning(f"Some products not found or inactive: {product_ids}")
                ORDER_FAILURE_COUNT.labels(reason="invalid_products").inc()
                raise HTTPException(400, "Some products not found or inactive")

            pmap = {p.id: p for p in products}

            total = 0
            order_items = []

            for item in payload.items:
                product = pmap.get(item.product_id)
                if not product:
                    ORDER_FAILURE_COUNT.labels(reason="product_not_found").inc()
                    raise HTTPException(400, f"Product {item.product_id} not found")

                total += product.price_rub * item.qty
                order_items.append(
                    {
                        "product_id": product.id,
                        "name_snapshot": product.name,
                        "price_rub_snapshot": product.price_rub,
                        "qty": item.qty,
                    }
                )

            # Добавляем стоимость доставки к итоговой сумме заказа
            config = db.query(MenuConfiguration).first()
            delivery_fee = config.delivery_fee if config else 0
            total_with_delivery = total + delivery_fee

            order = Order(
                customer_name=payload.name.strip(),
                phone_e164=phone_e164,
                address=payload.address.strip(),
                comment=payload.comment.strip() if payload.comment else None,
                idempotency_key=payload.idempotency_key,
                delivery_fee_rub=delivery_fee,
                total_rub=total_with_delivery,
                payment_method=PaymentMethod(payload.payment_method),
                delivery_mode=DeliveryMode(payload.delivery_mode),
                delivery_slot=payload.delivery_slot
                if payload.delivery_mode == "slot"
                else None,
                delivery_date=payload.delivery_date
                if payload.delivery_mode == "slot"
                else None,
                client_max_uid=payload.client_max_uid,
            )

            db.add(order)
            db.flush()

            # Генерация номера заказа: ГГ-ММ-ДД-00N
            today = date.today()
            prefix = today.strftime("%y-%m-%d")
            count_today = (
                db.query(func.count(Order.id))
                .filter(func.date(Order.created_at) == today)
                .scalar()
                or 0
            )
            order.order_number = f"{prefix}-{count_today:03d}"

            for item_data in order_items:
                order_item = OrderItem(order_id=order.id, **item_data)
                db.add(order_item)

            # YooKassa: создать платёж ДО commit, чтобы откатить при ошибке
            confirmation_url: str | None = None
            if payload.payment_method == "yookassa_card":
                try:
                    confirmation_url = create_yookassa_payment(order, db)
                except (YooKassaConfigError, YooKassaWebhookError) as e:
                    logger.error(f"YooKassa payment creation failed: {e}")
                    ORDER_FAILURE_COUNT.labels(reason="yookassa_error").inc()
                    raise HTTPException(502, "Платёжный сервис временно недоступен")

            ORDER_COUNT.inc()
            logger.info(
                f"Order {order.order_number} (id={order.id}) created successfully"
            )

            try:
                items_text = "\n".join(
                    f"• {item['name_snapshot']} x{item['qty']} = {item['price_rub_snapshot'] * item['qty']}₽"
                    for item in order_items
                )

                delivery_info = ""
                if order.delivery_mode.value == "slot":
                    delivery_info = (
                        f"\nСлот: {order.delivery_slot} ({order.delivery_date})"
                    )
                else:
                    delivery_info = "\nДоставка: как можно скорее"

                payment_method_label = {
                    "cash": "Наличные",
                    "sbp_transfer": "СБП",
                    "yookassa_card": "Банковская карта",
                }.get(order.payment_method.value, order.payment_method.value)

                subtotal = total  # сумма товаров без доставки
                delivery_fee_line = (
                    f"\n🚚 Доставка: {delivery_fee}₽"
                    if delivery_fee > 0
                    else "\n🚚 Доставка: бесплатно"
                )

                await notify_order_to_staff(
                    f"🛒 Новый заказ #{order.order_number}\n"
                    f"👤 {order.customer_name}\n"
                    f"📞 {order.phone_e164}\n"
                    f"📍 {order.address}\n"
                    f"💰 Оплата: {payment_method_label}\n"
                    f"{delivery_info}"
                    f"{delivery_fee_line}\n\n"
                    f"📦 Состав:\n{items_text}\n\n"
                    f"💵 Итого (с доставкой): {order.total_rub}₽",
                    order_id=order.id,
                    current_status=order.status,
                )

            except Exception as e:
                logger.error(f"Failed to send staff notification: {e}")

            return {
                "ok": True,
                "order_id": order.id,
                "confirmation_url": confirmation_url,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating order: {e}", exc_info=True)
            ORDER_FAILURE_COUNT.labels(reason="internal_error").inc()
            raise HTTPException(500, "Internal server error")


@app.post("/api/payments/webhook", tags=["Orders"])
async def payments_webhook(request: Request):
    """YooKassa IPN webhook: verify IP + signature, update order status."""
    client_ip = (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    if not _is_yookassa_ip(client_ip):
        logger.warning(f"YooKassa webhook blocked: unauthorized IP {client_ip}")
        raise HTTPException(403, "Forbidden")

    raw_body = await request.body()
    signature = request.headers.get("X-Content-SHA256")

    try:
        payload = request.json()  # уже прочитан через raw_body
        import json

        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    try:
        with SessionLocal.begin() as db:
            handle_yookassa_webhook(
                payload=payload,
                signature=signature,
                raw_body=raw_body,
                db=db,
            )
    except YooKassaWebhookError as e:
        logger.warning(f"YooKassa webhook rejected: {e}")
        raise HTTPException(400, str(e))
    except YooKassaConfigError as e:
        logger.error(f"YooKassa config error in webhook: {e}")
        raise HTTPException(500, "Internal error")

    return {"ok": True}


@app.get("/thanks/{order_id}", response_class=HTMLResponse, tags=["Orders"])
async def thanks_page(request: Request, order_id: int):
    """Order confirmation page"""
    with SessionLocal() as db:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(404, "Order not found")

        # Определяем, является ли заказ предзаказом вечернего меню (10:00-15:00)
        is_evening_preorder = False
        if order.delivery_mode.value == "asap" and order.created_at:
            # Конвертируем UTC в локальное время
            order_local_time = order.created_at.replace(tzinfo=None).replace(
                tzinfo=get_local_tz()
            )
            order_time = order_local_time.time()
            # Если заказ сделан между 10:00 и 15:00 - это предзаказ вечернего меню
            if EVENING_MENU_START <= order_time < EVENING_START:
                is_evening_preorder = True

        config = db.query(MenuConfiguration).first()
        config_delivery_fee = config.delivery_fee if config else 0
        # Используем delivery_fee_rub из заказа (если заказ создан после фикса),
        # иначе fallback на текущий config (для старых заказов)
        delivery_fee = (
            order.delivery_fee_rub
            if order.delivery_fee_rub is not None
            else config_delivery_fee
        )

        return templates.TemplateResponse(
            "thanks.html",
            {
                "request": request,
                "order": order,
                "asap_text": ASAP_TEXT,
                "is_evening_preorder": is_evening_preorder,
                "evening_delivery_start": EVENING_START.strftime("%H:%M"),
                "delivery_fee": delivery_fee,
                # total_rub уже включает доставку (после фикса)
                # для старых заказов: order.delivery_fee_rub is None — прибавляем из config
                "total_with_delivery": order.total_rub
                if order.delivery_fee_rub is not None
                else order.total_rub + config_delivery_fee,
            },
        )


@app.post("/api/max/callback", tags=["Orders"])
async def max_callback(request: Request):
    """
    MAX Platform webhook: обработка нажатий inline-кнопок смены статуса заказа.
    Для callback-кнопок MAX присылает событие message_callback, а payload кнопки
    передаётся в callback-объекте как строка payload; для совместимости оставляем
    fallback на data.
    """
    secret = request.headers.get("X-Max-Bot-Api-Secret")
    if settings.MAX_WEBHOOK_SECRET and secret != settings.MAX_WEBHOOK_SECRET:
        logger.warning("MAX callback: invalid webhook secret")
        raise HTTPException(status_code=403, detail="Forbidden")

    raw_body = await request.body()
    print(f"MAX RAW BODY: {raw_body.decode('utf-8', errors='replace')}")

    try:
        update = await request.json()
    except Exception as e:
        print(f"MAX JSON PARSE ERROR: {e!r}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    print(f"MAX PARSED UPDATE: {update!r}")

    if update.get("update_type") not in ("message_callback", "bot_started", "message_created"):
        print(f"MAX IGNORED UPDATE TYPE: {update.get('update_type')!r}")
        return JSONResponse({"ok": True, "ignored": True})

    # ── Клиентский /start ──────────────────────────────────────────────────────
    if update.get("update_type") in ("bot_started", "message_created"):
        sender = (update.get("message") or {}).get("sender") or {}
        # bot_started кладёт user прямо в update
        if not sender:
            sender = update.get("user") or {}
        try:
            user_id = int(sender.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0

        message_body = ((update.get("message") or {}).get("body") or {})
        text_in = (message_body.get("text") or "").strip()

        # Реагируем только на /start (или bot_started без текста)
        is_start = (
            update.get("update_type") == "bot_started"
            or text_in.lower() in ("/start", "start")
        )
        if is_start and user_id:
            menu_url = f"{settings.SITE_BASE_URL}/menu?max_uid={user_id}"
            await send_max_start_reply(
                user_id,
                menu_url=menu_url,
                welcome_text=settings.MAX_CLIENT_WELCOME,
            )
            logger.info("MAX /start reply sent to user_id=%s", user_id)
        elif user_id and update.get("update_type") == "message_created":
            # Fallback: любое другое сообщение — та же кнопка меню
            menu_url = f"{settings.SITE_BASE_URL}/menu?max_uid={user_id}"
            await send_max_start_reply(
                user_id,
                menu_url=menu_url,
                welcome_text="Нажмите кнопку ниже, чтобы открыть меню. 🍱",
            )
            logger.info("MAX fallback reply sent to user_id=%s", user_id)
        return JSONResponse({"ok": True})

    # ── Операторский callback (смена статуса) ──────────────────────────────────

    callback = update.get("callback") or {}
    print(f"MAX CALLBACK OBJECT: {callback!r}")

    callback_id: str | None = callback.get("callback_id")

    sender = callback.get("user") or {}
    try:
        sender_id: int | None = int(sender.get("user_id"))
    except (TypeError, ValueError):
        sender_id = None

    print(f"MAX CALLBACK SENDER: sender_id={sender_id!r}")

    if settings.MAX_ALLOWED_USER_IDS and sender_id not in settings.MAX_ALLOWED_USER_IDS:
        logger.warning("MAX callback: forbidden user_id=%s", sender_id)
        print(f"MAX ACL DENY: sender_id={sender_id!r}")
        if callback_id:
            await answer_max_callback(callback_id, notification="Недостаточно прав")
        raise HTTPException(status_code=403, detail="Forbidden")

    raw_payload = callback.get("payload")
    if raw_payload is None:
        raw_payload = callback.get("data")

    print(f"MAX CALLBACK PAYLOAD RAW: {raw_payload!r}")

    try:
        payload = json.loads(raw_payload or "")
    except (TypeError, json.JSONDecodeError) as e:
        print(f"MAX CALLBACK PAYLOAD JSON ERROR: {e!r}")
        if callback_id:
            await answer_max_callback(
                callback_id,
                notification="Некорректные данные кнопки",
            )
        raise HTTPException(status_code=400, detail="Invalid callback payload")

    print(f"MAX CALLBACK PAYLOAD PARSED: {payload!r}")

    order_id = payload.get("order_id")
    status_str = payload.get("status")

    if not order_id or not status_str:
        print(
            f"MAX CALLBACK PAYLOAD MISSING FIELDS: "
            f"order_id={order_id!r} status={status_str!r}"
        )
        if callback_id:
            await answer_max_callback(
                callback_id,
                notification="Недостаточно данных для смены статуса",
            )
        raise HTTPException(status_code=400, detail="Missing order_id or status")

    print(f"MAX CALLBACK TARGET: order_id={order_id!r} status={status_str!r}")

    resp = await update_order_status_endpoint(
        _MaxCallbackRequest(
            {"order_id": order_id, "status": status_str},
            headers=request.headers,
            client=request.client,
        )
    )

    try:
        body = json.loads(resp.body.decode("utf-8"))
    except Exception as e:
        print(f"MAX RESPONSE PARSE ERROR: {e!r}")
        body = {"success": False, "error": "Unknown response"}

    print(
        f"MAX UPDATE RESULT: order_id={order_id!r} "
        f"status={status_str!r} response={body!r}"
    )

    if callback_id:
        if body.get("success"):
            new_st = body.get("new_status", status_str)
            new_attachments = []
            msg_body = ((update.get("message") or {}).get("body") or {})
            current_text = msg_body.get("text") or f"Заказ #{order_id}"
            try:
                new_attachments = build_order_status_keyboard(
                    int(order_id),
                    OrderStatus(new_st),
                )
            except Exception as e:
                print(f"MAX KEYBOARD BUILD ERROR: {e!r}")

            print(
                f"MAX SUCCESS: order_id={order_id!r} "
                f"status={status_str!r} new_status={new_st!r}"
            )
            await answer_max_callback(
                callback_id,
                notification=f"Статус обновлён: {new_st}",
                message_text=current_text,
                attachments=new_attachments,
            )
        else:
            print(
                f"MAX ERROR: order_id={order_id!r} "
                f"status={status_str!r} error={body.get('error')!r}"
            )
            await answer_max_callback(
                callback_id,
                notification=body.get("error", "Не удалось обновить статус"),
            )

    return resp


class _MaxCallbackRequest:
    """Минимальная обёртка для передачи payload в update_order_status_endpoint."""

    def __init__(self, data: dict, headers=None, client=None) -> None:
        self._data = data
        self.headers = headers or {}
        self.client = client

    async def json(self) -> dict:
        return self._data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
