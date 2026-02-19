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


async def cache_get(key: str, request) -> Optional[str]:
    """Get value from cache"""
    redis = get_redis_client(request)
    if not redis:
        return None
    try:
        return await redis.get(key)
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
        return None


async def cache_set(key: str, value: str, request, ttl: int = 60):
    """Set value in cache with TTL"""
    redis = get_redis_client(request)
    if not redis:
        return
    try:
        await redis.setex(key, ttl, value)
    except Exception as e:
        logger.warning(f"Redis set error: {e}")


async def acquire_lock(key: str, request, ttl: int = 10) -> bool:
    """Try to acquire distributed lock"""
    redis = get_redis_client(request)
    if not redis:
        return True  # No redis = no lock needed
    try:
        lock_key = f"lock:{key}"
        # NX = only set if not exists
        result = await redis.set(lock_key, "1", nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        logger.warning(f"Redis lock error: {e}")
        return True


async def release_lock(key: str, request):
    """Release distributed lock"""
    redis = get_redis_client(request)
    if not redis:
        return
    try:
        lock_key = f"lock:{key}"
        await redis.delete(lock_key)
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
    from app.availability_models import AvailabilityScopeType
    with SessionLocal() as db:
        # Convert string to enum (lowercase to match DB enum values)
        scope_enum = AvailabilityScopeType(scope_type)
        rules = db.query(AvailabilityRule).filter(
            AvailabilityRule.scope_type == scope_enum,
            AvailabilityRule.scope_id == scope_id,
            AvailabilityRule.is_active == True
        ).all()
        return rules


def get_category_hierarchy_rules(category_id: int) -> List[AvailabilityRule]:
    """Get rules for category and its parents"""
    from app.availability_models import AvailabilityScopeType
    rules = []
    visited = set()
    
    with SessionLocal() as db:
        current_id = category_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            
            # Get rules for this category
            cat_rules = db.query(AvailabilityRule).filter(
                AvailabilityRule.scope_type == AvailabilityScopeType.category,
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


def convert_to_core_rule(rule: AvailabilityRule) -> Optional[CoreRule]:
    """Convert SQLAlchemy rule to core rule with error handling"""
    try:
        # Handle None daypart - default to ALLDAY
        if rule.daypart is None:
            daypart_val = Daypart.ALLDAY
        else:
            daypart_val = Daypart(rule.daypart.value)
        
        return CoreRule(
            id=rule.id,
            scope_type=str(rule.scope_type.value) if rule.scope_type else "product",
            scope_id=rule.scope_id,
            daypart=daypart_val,
            lead_time_minutes=rule.lead_time_minutes or 0,
            methods=rule.methods or [],
            allow_tomorrow=rule.allow_tomorrow if rule.allow_tomorrow is not None else True,
            tomorrow_cutoff=rule.tomorrow_cutoff or time(23, 0),
            is_active=rule.is_active if rule.is_active is not None else True,
            start_time=rule.start_time,
            end_time=rule.end_time
        )
    except Exception as e:
        logger.error(f"Error converting rule {rule.id}: {e}")
        return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/slots", response_model=SlotsResponse)
async def get_available_slots(
    request: Request,
    day: str = Query(..., regex="^(today|tomorrow)$"),
    method: str = Query(..., regex="^(delivery|pickup)$")
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
    cached = await cache_get(cache_key, request)
    if cached:
        try:
            data = json.loads(cached)
            logger.debug(f"Slots cache hit: {cache_key}")
            return SlotsResponse(**data)
        except Exception as e:
            logger.warning(f"Cache parse error: {e}")
    
    # Cache miss - acquire lock to prevent stampede
    if not await acquire_lock(cache_key, request):
        # Another process is generating, wait and retry cache
        import asyncio
        await asyncio.sleep(0.5)
        cached = await cache_get(cache_key, request)
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
        await cache_set(cache_key, response.json(), request, settings.MENU_CACHE_TTL)
        
        return response
        
    finally:
        await release_lock(cache_key, request)


@router.get("/menu", response_model=MenuResponse)
async def get_menu(
    request: Request,
    day: str = Query("today", regex="^(today|tomorrow)$"),
    method: str = Query(..., regex="^(delivery|pickup)$"),
    slot: Optional[str] = Query(None, regex="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
):
    """
    Get menu with computed availability for each product.
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
    cached = await cache_get(cache_key, request)
    if cached:
        try:
            data = json.loads(cached)
            return MenuResponse(**data)
        except:
            pass
    
    # Cache miss logic...
    if not await acquire_lock(cache_key, request):
        import asyncio
        await asyncio.sleep(0.5)
        cached = await cache_get(cache_key, request)
        if cached:
            try:
                data = json.loads(cached)
                return MenuResponse(**data)
            except:
                pass
    
    try:
        categories_data = []
        with SessionLocal() as db:
            # 1. Fetch all rules once to avoid N+1 queries
            all_rules_db = db.query(AvailabilityRule).filter(AvailabilityRule.is_active == True).all()
            all_core_rules = [r for r in (convert_to_core_rule(rule) for rule in all_rules_db) if r is not None]
            
            # Map rules by scope
            product_rules_map = {}
            category_rules_map = {}
            for rule in all_core_rules:
                if rule.scope_type == 'product':
                    product_rules_map.setdefault(rule.scope_id, []).append(rule)
                else:
                    category_rules_map.setdefault(rule.scope_id, []).append(rule)
            
            # 2. Fetch categories and products
            root_cats = db.query(Category).filter(
                Category.is_active == True,
                Category.parent_id == None
            ).order_by(Category.sort).all()
            
            # Category hierarchy cache
            cat_map = {c.id: c for c in db.query(Category).filter(Category.is_active == True).all()}
            
            for root_cat in root_cats:
                cat_products = []
                
                def process_category_products(cat):
                    # Direct products
                    products = db.query(Product).filter(
                        Product.category_id == cat.id,
                        Product.is_active == True
                    ).all()
                    
                    for product in products:
                        try:
                            # Get rules for product
                            p_rules = product_rules_map.get(product.id, [])
                            
                            # Get rules for category hierarchy
                            c_rules = []
                            curr_cat_id = cat.id
                            visited_cats = set()
                            while curr_cat_id and curr_cat_id not in visited_cats:
                                visited_cats.add(curr_cat_id)
                                c_rules.extend(category_rules_map.get(curr_cat_id, []))
                                curr_cat = cat_map.get(curr_cat_id)
                                curr_cat_id = curr_cat.parent_id if curr_cat else None
                            
                            # Check availability
                            result = check_availability(
                                product_rules=p_rules,
                                category_rules=c_rules,
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
                        except Exception as e:
                            import traceback
                            logger.error(f"Error checking availability for product {product.id} ({product.name}): {e}")
                            logger.error(traceback.format_exc())
                            # Add with default unavailable state to prevent 500
                            cat_products.append(MenuItemAvailability(
                                product_id=product.id,
                                name=product.name,
                                price_rub=product.price_rub,
                                available=False,
                                next_available=None,
                                reason_code="ERROR",
                                badge_text="Ошибка",
                                cta_type="unavailable"
                            ))
                    
                    # Subcategories
                    for child in cat.children:
                        if child.is_active:
                            process_category_products(child)
                
                process_category_products(root_cat)
                
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
        
        await cache_set(cache_key, response.json(), request, settings.MENU_CACHE_TTL)
        return response
        
    except Exception as e:
        logger.error(f"Error in get_menu: {e}", exc_info=True)
        raise HTTPException(500, "Internal server error while building menu")
    finally:
        await release_lock(cache_key, request)


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
