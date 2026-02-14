"""
Sieshka Food Delivery API v3.0.0

Low Priority Fixes:
- Compression middleware for responses
- Proper CORS configuration
- API documentation with OpenAPI tags
- Version endpoint
- Configuration management via pydantic-settings
"""
import os
import sys
import uuid
import bleach
import logging
import signal
from datetime import datetime, time, date, timedelta
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from typing import Any, Optional
from functools import wraps

from fastapi import FastAPI, Request, HTTPException, Query, Depends, APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from cachetools import TTLCache

# Low Priority Fix: Import from config module
from config import settings
from config.constants import VERSION, MAX_QTY_PER_ITEM, MAX_ITEMS_IN_CART

from .db import engine, SessionLocal
from .models import Base, Category, Product, Order, OrderItem, PaymentMethod, DeliveryMode, MenuPeriod, DeliverySlot
from .telegram import notify_both, retry_failed_notifications, get_failed_notifications_count
from .admin import setup_admin
from .schemas import OrderCreate, HealthResponse, DeliverySlotsAvailability, DeliverySlotResponse

# Structured logging with correlation IDs
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(record, 'request_id', 'N/A')
        return True

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
ORDER_COUNT = Counter('orders_created_total', 'Total orders created')
ORDER_FAILURE_COUNT = Counter('orders_failed_total', 'Total order failures', ['reason'])

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
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' https://cdn.jsdelivr.net;"
    return response

# Request/Response logging middleware
async def request_response_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = datetime.now()
    
    body = await request.body()
    logger.info(f"[{request_id}] Request {request.method} {request.url.path} - Body: {body[:1000] if body else 'empty'}")
    
    try:
        response = await call_next(request)
        duration = (datetime.now() - start_time).total_seconds()
        
        REQUEST_COUNT.labels(
            method=request.method, 
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        REQUEST_DURATION.observe(duration)
        
        logger.info(f"[{request_id}] Response {response.status_code} in {duration:.3f}s")
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Request failed: {e}", exc_info=True)
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Application v{VERSION} starting up...")
    yield
    logger.info("Application shutting down...")

# Low Priority Fix: Create FastAPI app with OpenAPI metadata
app = FastAPI(
    title=settings.APP_NAME,
    description="Food Delivery API for Sieshka restaurant",
    version=VERSION,
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
    openapi_url="/openapi.json" if settings.ENV != "production" else None,
    lifespan=lifespan
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
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=settings.ALLOWED_HOSTS
)

# Rate limiting with phone number tracking
class PhoneRateLimiter:
    def __init__(self):
        self.requests = {}
        self.window = 60
        self.max_requests = settings.PHONE_RATE_LIMIT_PER_MINUTE
    
    def is_allowed(self, phone: str) -> bool:
        now = datetime.now()
        key = phone
        
        if key not in self.requests:
            self.requests[key] = []
        
        self.requests[key] = [t for t in self.requests[key] if now - t < timedelta(seconds=self.window)]
        
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        self.requests[key].append(now)
        return True

phone_rate_limiter = PhoneRateLimiter()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"Rate limit exceeded for {request.client.host if request.client else 'unknown'}")
    ORDER_FAILURE_COUNT.labels(reason="rate_limit").inc()
    return JSONResponse(
        {"detail": "Too many requests, please try again later"}, 
        status_code=429
    )

# Templates with autoescape enabled
templates = Jinja2Templates(directory="app/templates")
templates.env.autoescape = True

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

TZ_NAME = settings.TZ_NAME
LOCAL_TZ = ZoneInfo(TZ_NAME)

MORNING_START = _parse_hhmm(settings.MORNING_START)
MORNING_END   = _parse_hhmm(settings.MORNING_END)
EVENING_MENU_START = _parse_hhmm(settings.EVENING_MENU_START)  # Время показа вечернего меню
EVENING_START = _parse_hhmm(settings.EVENING_START)  # Время начала доставки вечернего меню
EVENING_END   = _parse_hhmm(settings.EVENING_END)

ASAP_TEXT = settings.ASAP_TEXT

MAX_QTY = MAX_QTY_PER_ITEM
MAX_ITEMS = MAX_ITEMS_IN_CART

# Setup admin
setup_admin(app, engine)

def normalize_ru_phone(phone_raw: str) -> str:
    try:
        num = phonenumbers.parse(phone_raw, None)
    except NumberParseException:
        raise HTTPException(400, "Телефон не распознан, используйте формат +7XXXXXXXXXX")

    if num.country_code != 7:
        raise HTTPException(400, "Нужен телефон РФ (+7)")

    if not phonenumbers.is_valid_number(num):
        raise HTTPException(400, "Телефон недействителен")

    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)

def get_current_menu_period(now: datetime) -> str | None:
    """Определяет какое меню показывать (morning/evening)"""
    t = now.time()
    if MORNING_START <= t <= MORNING_END:
        return "morning"
    if EVENING_MENU_START <= t <= EVENING_END:
        return "evening"
    return None

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
    slot = db.query(DeliverySlot).filter(
        DeliverySlot.slot_time == slot_time,
        DeliverySlot.is_active == True
    ).first()
    
    if not slot:
        return False
    
    current_orders = db.query(Order).filter(
        Order.delivery_slot == slot_time,
        Order.delivery_date == delivery_date,
        Order.status.notin_(["cancelled"])
    ).count()
    
    return current_orders < slot.max_orders

def get_slot_availability(db, target_date: date) -> list:
    slots = db.query(DeliverySlot).filter(DeliverySlot.is_active == True).all()
    availability = []
    
    for slot in slots:
        current_orders = db.query(Order).filter(
            Order.delivery_slot == slot.slot_time,
            Order.delivery_date == target_date,
            Order.status.notin_(["cancelled"])
        ).count()
        
        availability.append({
            "slot_time": slot.slot_time,
            "max_orders": slot.max_orders,
            "current_orders": current_orders,
            "available": current_orders < slot.max_orders
        })
    
    return availability

# Low Priority Fix: Version endpoint
@app.get("/version", tags=["System"])
async def get_version():
    """Get application version information"""
    return {
        "version": VERSION,
        "app_name": settings.APP_NAME,
        "environment": settings.ENV,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/health", tags=["System"], response_model=HealthResponse)
async def health():
    """Health check endpoint for monitoring"""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return HealthResponse(
            status="ok",
            version=VERSION,
            database="connected",
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            {"status": "error", "detail": "Database connection failed"},
            status_code=503
        )

@app.get("/admin/diagnostics", tags=["System"])
async def diagnostics():
    """System diagnostics for administrators"""
    return {
        "version": VERSION,
        "failed_notifications": get_failed_notifications_count(),
        "time": datetime.utcnow().isoformat(),
        "menu_available": is_menu_available(datetime.now(LOCAL_TZ))
    }

@app.get("/api/slots/availability", response_model=DeliverySlotsAvailability, tags=["Delivery"])
async def get_slots_availability(target_date: date = Query(default_factory=date.today)):
    """Get delivery slot availability for a specific date"""
    if target_date < date.today():
        raise HTTPException(400, "Cannot check availability for past dates")
    
    with SessionLocal() as db:
        slots = get_slot_availability(db, target_date)
        return DeliverySlotsAvailability(
            date=target_date,
            slots=[DeliverySlotResponse(**slot) for slot in slots]
        )

@app.get("/", response_class=HTMLResponse, tags=["Menu"])
async def index(request: Request, preview_period: str = Query(None)):
    """Main menu page"""
    now = datetime.now(LOCAL_TZ)
    
    if preview_period in ("morning", "evening"):
        current_period = preview_period
    else:
        current_period = get_current_menu_period(now)
    
    if current_period is None and not preview_period:
        return templates.TemplateResponse("closed.html", {
            "request": request,
            "morning_start": MORNING_START.strftime("%H:%M"),
            "morning_end": MORNING_END.strftime("%H:%M"),
            "evening_start": EVENING_START.strftime("%H:%M"),
            "evening_end": EVENING_END.strftime("%H:%M"),
        })
    
    cache_key = f"menu_{current_period}_{preview_period}"
    cached_data = menu_cache.get(cache_key)
    
    if cached_data:
        logger.debug(f"Serving menu from cache: {cache_key}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            **cached_data
        })
    
    with SessionLocal() as db:
        # Load only root categories (no parent) and their subcategories
        root_cats = db.query(Category).filter(
            Category.is_active == True,
            Category.parent_id == None
        ).order_by(Category.sort).all()
        
        # Build hierarchical structure
        categories_data = []
        
        for root_cat in root_cats:
            cat_data = {
                'category': root_cat,
                'subcategories': [],
                'products': []
            }
            
            # Get products directly in this category
            direct_products = db.query(Product).filter(
                Product.category_id == root_cat.id,
                Product.is_active == True
            ).all()
            
            for p in direct_products:
                period = p.menu_period_override or root_cat.menu_period
                if period == MenuPeriod.both or period.value == current_period:
                    cat_data['products'].append(p)
            
            # Get subcategories and their products
            for subcat in root_cat.children:
                if not subcat.is_active:
                    continue
                    
                subcat_data = {
                    'category': subcat,
                    'products': []
                }
                
                subcat_products = db.query(Product).filter(
                    Product.category_id == subcat.id,
                    Product.is_active == True
                ).all()
                
                for p in subcat_products:
                    period = p.menu_period_override or subcat.menu_period
                    if period == MenuPeriod.both or period.value == current_period:
                        subcat_data['products'].append(p)
                
                if subcat_data['products']:
                    cat_data['subcategories'].append(subcat_data)
            
            # Only add category if it has products or subcategories with products
            if cat_data['products'] or cat_data['subcategories']:
                categories_data.append(cat_data)
    
    data = {
        "categories_data": categories_data,
        "current_period_label": current_period,
        "preview_period": preview_period,
    }
    
    menu_cache[cache_key] = data
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        **data
    })

@app.get("/cart", response_class=HTMLResponse, tags=["Menu"])
async def cart_page(request: Request):
    """Shopping cart page"""
    return templates.TemplateResponse("cart.html", {"request": request})

@app.get("/checkout", response_class=HTMLResponse, tags=["Orders"])
async def checkout_page(request: Request):
    """Checkout page"""
    now = datetime.now(LOCAL_TZ)
    current_menu_period = get_current_menu_period(now)
    current_delivery_period = get_current_period_label(now)
    
    # Проверяем доступность меню (меню доступно с 10:00 для вечернего)
    if current_menu_period is None:
        return templates.TemplateResponse("closed.html", {
            "request": request,
            "morning_start": MORNING_START.strftime("%H:%M"),
            "morning_end": MORNING_END.strftime("%H:%M"),
            "evening_start": EVENING_START.strftime("%H:%M"),
            "evening_end": EVENING_END.strftime("%H:%M"),
        })
    
    # Определяем, показывать ли предупреждение о доставке после 15:00
    # Это нужно когда меню evening, но доставка еще не началась (10:00-15:00)
    show_delivery_notice = (current_menu_period == "evening" and current_delivery_period is None)
    
    return templates.TemplateResponse("checkout.html", {
        "request": request,
        "delivery_slots": DELIVERY_SLOTS,
        "current_menu_period": current_menu_period,
        "show_delivery_notice": show_delivery_notice,
        "evening_delivery_start": EVENING_START.strftime("%H:%M"),
    })

@app.post("/api/orders", tags=["Orders"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_order(request: Request, payload: OrderCreate):
    """Create a new order with idempotency protection and slot validation"""
    logger.info(f"Creating order from {request.client.host if request.client else 'unknown'}")
    
    try:
        phone_e164 = normalize_ru_phone(payload.phone)
    except HTTPException:
        ORDER_FAILURE_COUNT.labels(reason="invalid_phone").inc()
        raise
    
    if not phone_rate_limiter.is_allowed(phone_e164):
        logger.warning(f"Phone rate limit exceeded for {phone_e164}")
        ORDER_FAILURE_COUNT.labels(reason="phone_rate_limit").inc()
        raise HTTPException(429, "Слишком много заказов с этого номера. Попробуйте позже.")
    
    with SessionLocal.begin() as db:
        try:
            existing = db.query(Order).filter(
                Order.idempotency_key == payload.idempotency_key
            ).first()
            
            if existing:
                logger.info(f"Returning existing order {existing.id} for idempotency key")
                return {"ok": True, "order_id": existing.id, "existing": True}
            
            if payload.delivery_mode == "slot":
                if not check_slot_availability(db, payload.delivery_slot, payload.delivery_date):
                    ORDER_FAILURE_COUNT.labels(reason="slot_unavailable").inc()
                    raise HTTPException(400, "Выбранный слот доставки заполнен. Выберите другой.")
            
            product_ids = [i.product_id for i in payload.items]
            products = db.query(Product).filter(
                Product.id.in_(product_ids),
                Product.is_active == True
            ).all()
            
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
                order_items.append({
                    "product_id": product.id,
                    "name_snapshot": product.name,
                    "price_rub_snapshot": product.price_rub,
                    "qty": item.qty
                })
            
            order = Order(
                customer_name=payload.name.strip(),
                phone_e164=phone_e164,
                address=payload.address.strip(),
                comment=payload.comment.strip() if payload.comment else None,
                idempotency_key=payload.idempotency_key,
                total_rub=total,
                payment_method=PaymentMethod(payload.payment_method),
                delivery_mode=DeliveryMode(payload.delivery_mode),
                delivery_slot=payload.delivery_slot if payload.delivery_mode == "slot" else None,
                delivery_date=payload.delivery_date if payload.delivery_mode == "slot" else None,
            )
            
            db.add(order)
            db.flush()
            
            for item_data in order_items:
                order_item = OrderItem(order_id=order.id, **item_data)
                db.add(order_item)
            
            ORDER_COUNT.inc()
            logger.info(f"Order {order.id} created successfully")
            
            try:
                await notify_both(
                    f"Новый заказ #{order.id}\n"
                    f"Телефон: {order.phone_e164}\n"
                    f"Сумма: {order.total_rub}₽\n"
                    f"Адрес: {order.address}"
                )
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
            
            return {"ok": True, "order_id": order.id}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating order: {e}", exc_info=True)
            ORDER_FAILURE_COUNT.labels(reason="internal_error").inc()
            raise HTTPException(500, "Internal server error")

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
        order_local_time = order.created_at.replace(tzinfo=None).replace(tzinfo=LOCAL_TZ)
        order_time = order_local_time.time()
        # Если заказ сделан между 10:00 и 15:00 - это предзаказ вечернего меню
        if EVENING_MENU_START <= order_time < EVENING_START:
            is_evening_preorder = True
    
    return templates.TemplateResponse("thanks.html", {
        "request": request,
        "order": order,
        "asap_text": ASAP_TEXT,
        "is_evening_preorder": is_evening_preorder,
        "evening_delivery_start": EVENING_START.strftime("%H:%M"),
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
