"""
Time-First Menu API Endpoints
Implements /api/slots and /api/menu with Redis caching.
"""
import json
import logging
from datetime import datetime, time
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from config.constants import (
    REASON_OUTSIDE_WINDOW, REASON_LEAD_TIME, REASON_METHOD_NOT_ALLOWED,
    REASON_TOMORROW_CUTOFF, REASON_INACTIVE, REASON_NO_RULE
)

from app.db import SessionLocal
from app.models import Category, Product
from app.availability_models import AvailabilityRule, MenuConfiguration
from app.timefirst_core import (
    Daypart, DeliveryMethod, get_slots, check_availability,
    AvailabilityRule as CoreRule, format_next_available,
    UnavailabilityReason
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["timefirst"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SlotResponse(BaseModel):
    time: str
    available: bool
    label: str


class SlotsResponse(BaseModel):
    day: str
    method: str
    slots: List[SlotResponse]
    error: Optional[str] = None


class MenuItemAvailability(BaseModel):
    product_id: int
    name: str
    price_rub: int
    available: bool
    next_available: Optional[str]
    reason_code: Optional[str]
    badge_text: str
    cta_type: str


class MenuCategoryResponse(BaseModel):
    category_id: int
    name: str
    products: List[MenuItemAvailability]


class MenuResponse(BaseModel):
    day: str
    method: str
    slot: Optional[str]
    categories: List[MenuCategoryResponse]
    generated_at: str


# ============================================================================
# Redis Cache Helpers
# ============================================================================

def get_redis_client(request):
    """Get Redis client from app state via request"""
    if request is None:
        return None
    return getattr(request.app.state, 'redis', None)


def cache_get(key: str, request) -> Optional[str]:
    """Get value from cache"""
    redis = get_redis_client(request)
    if not redis:
        return None
    try:
        return redis.get(key)
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
        return None


def cache_set(key: str, value: str, request, ttl: int = 60):
    """Set value in cache with TTL"""
    redis = get_redis_client(request)
    if not redis:
        return
    try:
        redis.setex(key, ttl, value)
    except Exception as e:
        logger.warning(f"Redis set error: {e}")


def acquire_lock(key: str, request, ttl: int = 10) -> bool:
    """Try to acquire distributed lock"""
    redis = get_redis_client(request)
    if not redis:
        return True  # No redis = no lock needed
    try:
        lock_key = f"lock:{key}"
        # NX = only set if not exists
        result = redis.set(lock_key, "1", nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        logger.warning(f"Redis lock error: {e}")
        return True


def release_lock(key: str, request):
    """Release distributed lock"""
    redis = get_redis_client(request)
    if not redis:
        return
    try:
        lock_key = f"lock:{key}"
        redis.delete(lock_key)
    except Exception as e:
        logger.warning(f"Redis unlock error: {e}")


# ============================================================================
# Cache Key Generation
# ============================================================================

def get_menu_cache_key(day: str, method: str, slot: Optional[str], tz: str, version: int) -> str:
    """Generate cache key for menu"""
    slot_part = slot or "asap"
    return f"menu:{day}:{method}:{slot_part}:{tz}:{version}"


def get_slots_cache_key(day: str, method: str, tz: str, version: int) -> str:
    """Generate cache key for slots"""
    return f"slots:{day}:{method}:{tz}:{version}"


# ============================================================================
# Database Helpers
# ============================================================================

def get_menu_config() -> MenuConfiguration:
    """Get or create menu configuration"""
    with SessionLocal() as db:
        config = db.query(MenuConfiguration).first()
        if not config:
            config = MenuConfiguration()
            db.add(config)
            db.commit()
            db.refresh(config)
        return config


def get_availability_rules(scope_type: str, scope_id: int) -> List[AvailabilityRule]:
    """Get active availability rules for scope"""
    with SessionLocal() as db:
        rules = db.query(AvailabilityRule).filter(
            AvailabilityRule.scope_type == scope_type,
            AvailabilityRule.scope_id == scope_id,
            AvailabilityRule.is_active == True
        ).all()
        return rules


def get_category_hierarchy_rules(category_id: int) -> List[AvailabilityRule]:
    """Get rules for category and its parents"""
    rules = []
    visited = set()
    
    with SessionLocal() as db:
        current_id = category_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            
            # Get rules for this category
            cat_rules = db.query(AvailabilityRule).filter(
                AvailabilityRule.scope_type == 'category',
                AvailabilityRule.scope_id == current_id,
                AvailabilityRule.is_active == True
            ).all()
            rules.extend(cat_rules)
            
            # Get parent
            category = db.query(Category).filter(Category.id == current_id).first()
            if category:
                current_id = category.parent_id
            else:
                break
    
    return rules


def convert_to_core_rule(rule: AvailabilityRule) -> CoreRule:
    """Convert SQLAlchemy rule to core rule"""
    return CoreRule(
        id=rule.id,
        scope_type=rule.scope_type,
        scope_id=rule.scope_id,
        daypart=Daypart(rule.daypart.value),
        lead_time_minutes=rule.lead_time_minutes,
        methods=rule.methods,
        allow_tomorrow=rule.allow_tomorrow,
        tomorrow_cutoff=rule.tomorrow_cutoff,
        is_active=rule.is_active,
        start_time=rule.start_time,
        end_time=rule.end_time
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/slots", response_model=SlotsResponse)
async def get_available_slots(
    day: str = Query(..., regex="^(today|tomorrow)$"),
    method: str = Query(..., regex="^(delivery|pickup)$"),
    request: Request = None
):
    """
    Get available delivery/pickup slots for a given day.
    
    - **day**: 'today' or 'tomorrow'
    - **method**: 'delivery' or 'pickup'
    
    Returns list of 15-minute slots within MORNING (07-10) and EVENING (14-21) windows.
    """
    config = get_menu_config()
    tz = ZoneInfo(config.business_tz)
    now = datetime.now(tz)
    
    # Generate cache key
    cache_key = get_slots_cache_key(day, method, config.business_tz, config.menu_version)
    
    # Try cache first
    cached = cache_get(cache_key, request)
    if cached:
        try:
            data = json.loads(cached)
            logger.debug(f"Slots cache hit: {cache_key}")
            return SlotsResponse(**data)
        except Exception as e:
            logger.warning(f"Cache parse error: {e}")
    
    # Cache miss - acquire lock to prevent stampede
    if not acquire_lock(cache_key, request):
        # Another process is generating, wait and retry cache
        import asyncio
        await asyncio.sleep(0.5)
        cached = cache_get(cache_key, request)
        if cached:
            try:
                data = json.loads(cached)
                return SlotsResponse(**data)
            except:
                pass
    
    try:
        # Generate slots
        slots, error = get_slots(
            target_day=day,
            method=DeliveryMethod(method),
            now=now,
            interval_minutes=config.slot_interval_minutes,
            base_buffer_minutes=config.base_buffer_minutes,
            tomorrow_cutoff=config.tomorrow_order_cutoff if config.enable_tomorrow_orders else time(0, 0)
        )
        
        response = SlotsResponse(
            day=day,
            method=method,
            slots=[
                SlotResponse(
                    time=s.time.strftime("%H:%M"),
                    available=s.available,
                    label=s.label
                ) for s in slots
            ],
            error=error
        )
        
        # Cache the result
        cache_set(cache_key, response.json(), request, settings.MENU_CACHE_TTL)
        
        return response
        
    finally:
        release_lock(cache_key, request)


@router.get("/menu", response_model=MenuResponse)
async def get_menu(
    day: str = Query(..., regex="^(today|tomorrow)$"),
    method: str = Query(..., regex="^(delivery|pickup)$"),
    slot: Optional[str] = Query(None, regex="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"),
    request: Request = None
):
    """
    Get menu with computed availability for each product.
    
    - **day**: 'today' or 'tomorrow'
    - **method**: 'delivery' or 'pickup'
    - **slot**: Optional specific slot (HH:MM format). If not provided, uses ASAP logic.
    
    Returns categories with products and their availability status.
    """
    config = get_menu_config()
    tz = ZoneInfo(config.business_tz)
    now = datetime.now(tz)
    
    # Parse slot if provided
    desired_slot = None
    if slot:
        try:
            hour, minute = map(int, slot.split(':'))
            desired_slot = time(hour, minute)
        except ValueError:
            raise HTTPException(400, "Invalid slot format. Use HH:MM")
    
    # Generate cache key
    cache_key = get_menu_cache_key(day, method, slot, config.business_tz, config.menu_version)
    
    # Try cache first
    cached = cache_get(cache_key, request)
    if cached:
        try:
            data = json.loads(cached)
            logger.debug(f"Menu cache hit: {cache_key}")
            return MenuResponse(**data)
        except Exception as e:
            logger.warning(f"Cache parse error: {e}")
    
    # Cache miss - acquire lock
    if not acquire_lock(cache_key, request):
        import asyncio
        await asyncio.sleep(0.5)
        cached = cache_get(cache_key, request)
        if cached:
            try:
                data = json.loads(cached)
                return MenuResponse(**data)
            except:
                pass
    
    try:
        # Build menu with availability
        categories_data = []
        
        with SessionLocal() as db:
            # Get all active root categories
            root_cats = db.query(Category).filter(
                Category.is_active == True,
                Category.parent_id == None
            ).order_by(Category.sort).all()
            
            for root_cat in root_cats:
                cat_products = []
                
                # Get all products in this category tree
                def get_products_recursive(cat):
                    products = []
                    # Direct products
                    direct = db.query(Product).filter(
                        Product.category_id == cat.id,
                        Product.is_active == True
                    ).all()
                    products.extend(direct)
                    
                    # Subcategory products
                    for child in cat.children:
                        if child.is_active:
                            products.extend(get_products_recursive(child))
                    
                    return products
                
                all_products = get_products_recursive(root_cat)
                
                for product in all_products:
                    # Get rules
                    product_rules_db = get_availability_rules('product', product.id)
                    category_rules_db = get_category_hierarchy_rules(product.category_id)
                    
                    # Convert to core rules
                    product_rules = [convert_to_core_rule(r) for r in product_rules_db]
                    category_rules = [convert_to_core_rule(r) for r in category_rules_db]
                    
                    # Check availability
                    result = check_availability(
                        product_rules=product_rules,
                        category_rules=category_rules,
                        day=day,
                        method=DeliveryMethod(method),
                        now=now,
                        desired_slot=desired_slot,
                        tomorrow_cutoff=config.tomorrow_order_cutoff if config.enable_tomorrow_orders else time(0, 0)
                    )
                    
                    cat_products.append(MenuItemAvailability(
                        product_id=product.id,
                        name=product.name,
                        price_rub=product.price_rub,
                        available=result.available,
                        next_available=format_next_available(result.next_available) if result.next_available else None,
                        reason_code=result.reason_code.value if result.reason_code else None,
                        badge_text=result.badge_text,
                        cta_type=result.cta_type
                    ))
                
                if cat_products:
                    categories_data.append(MenuCategoryResponse(
                        category_id=root_cat.id,
                        name=root_cat.name,
                        products=cat_products
                    ))
        
        response = MenuResponse(
            day=day,
            method=method,
            slot=slot,
            categories=categories_data,
            generated_at=now.isoformat()
        )
        
        # Cache the result
        cache_set(cache_key, response.json(), request, settings.MENU_CACHE_TTL)
        
        return response
        
    finally:
        release_lock(cache_key, request)


@router.get("/menu/refresh")
async def refresh_menu_cache():
    """
    Admin endpoint to refresh menu cache.
    Bumps menu version to invalidate all cached entries.
    """
    with SessionLocal() as db:
        config = db.query(MenuConfiguration).first()
        if config:
            config.menu_version += 1
            db.commit()
            return {"message": "Menu cache refreshed", "new_version": config.menu_version}
        else:
            raise HTTPException(500, "Menu configuration not found")
