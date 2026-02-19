"""
Time-First Menu Core Module
Pure functions for slot generation and availability checking.
No external dependencies - can be tested in isolation.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, date
from typing import Optional, List, Tuple
from enum import Enum
import math


class Daypart(str, Enum):
    MORNING = "MORNING"
    EVENING = "EVENING"
    ALLDAY = "ALLDAY"


class DeliveryMethod(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"


class UnavailabilityReason(str, Enum):
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    LEAD_TIME = "LEAD_TIME"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    TOMORROW_CUTOFF = "TOMORROW_CUTOFF"
    INACTIVE = "INACTIVE"
    NO_RULE = "NO_RULE"


@dataclass
class TimeWindow:
    """Time window for daypart"""
    start: time
    end: time
    
    def contains(self, t: time) -> bool:
        """Check if time falls within window"""
        return self.start <= t <= self.end


@dataclass
class AvailabilityRule:
    """Simplified rule for core logic (not SQLAlchemy model)"""
    id: int
    scope_type: str  # 'product' or 'category'
    scope_id: int
    daypart: Daypart
    lead_time_minutes: int
    methods: List[str]  # ['delivery'], ['pickup'], ['delivery', 'pickup']
    allow_tomorrow: bool
    tomorrow_cutoff: time
    is_active: bool
    # Optional explicit time window
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    
    def get_effective_window(self) -> TimeWindow:
        """Get effective time window"""
        if self.start_time and self.end_time:
            return TimeWindow(self.start_time, self.end_time)
        
        # Default windows based on daypart
        if self.daypart == Daypart.MORNING:
            return TimeWindow(time(7, 0), time(10, 0))
        elif self.daypart == Daypart.EVENING:
            return TimeWindow(time(14, 0), time(21, 0))
        else:  # ALLDAY
            return TimeWindow(time(0, 0), time(23, 59))
    
    def allows_method(self, method: DeliveryMethod) -> bool:
        return method.value in self.methods


@dataclass
class AvailabilityResult:
    """Result of availability check"""
    available: bool
    next_available: Optional[datetime]
    reason_code: Optional[UnavailabilityReason]
    badge_text: str
    cta_type: str  # 'add_to_cart', 'select_time', 'preorder', 'unavailable'


@dataclass
class Slot:
    """Delivery/pickup slot"""
    time: time
    available: bool
    label: str


# ============================================================================
# SLOT GENERATION
# ============================================================================

def ceil_to_interval(dt: datetime, interval_minutes: int = 15) -> datetime:
    """
    Round datetime UP to nearest interval.
    Example: 08:07 -> 08:15 (with interval=15)
    """
    minutes = dt.minute
    seconds = dt.second
    microseconds = dt.microsecond
    
    # Total minutes to add
    total_minutes = minutes + seconds / 60 + microseconds / 3600000
    intervals = math.ceil(total_minutes / interval_minutes)
    
    # Reset to hour start, then add intervals
    result = dt.replace(minute=0, second=0, microsecond=0)
    result += timedelta(minutes=intervals * interval_minutes)
    
    return result


def generate_slots_for_window(
    window: TimeWindow,
    base_time: datetime,
    interval_minutes: int = 15,
    base_buffer_minutes: int = 15
) -> List[Slot]:
    """
    Generate slots within a time window.
    
    Args:
        window: Time window to generate slots for
        base_time: Reference time (usually now, rounded up)
        interval_minutes: Slot interval (default 15 min)
        base_buffer_minutes: Minimum buffer from base_time (default 15 min)
    
    Returns:
        List of Slot objects
    """
    slots = []
    
    # Calculate minimum allowed time (base_time + buffer)
    min_time = base_time + timedelta(minutes=base_buffer_minutes)
    
    # Start from window start or min_time, whichever is later
    current_date = base_time.date()
    window_start_dt = datetime.combine(current_date, window.start)
    window_end_dt = datetime.combine(current_date, window.end)
    
    # Add timezone to window times (match base_time timezone)
    from zoneinfo import ZoneInfo
    tz = base_time.tzinfo
    window_start_dt = window_start_dt.replace(tzinfo=tz)
    window_end_dt = window_end_dt.replace(tzinfo=tz)
    
    # Round window start to interval
    slot_time = ceil_to_interval(window_start_dt, interval_minutes)
    
    while slot_time <= window_end_dt:
        slot_time_only = slot_time.time()
        
        # Check if slot is in the future (with buffer)
        is_available = slot_time >= min_time
        
        slots.append(Slot(
            time=slot_time_only,
            available=is_available,
            label=slot_time_only.strftime("%H:%M")
        ))
        
        slot_time += timedelta(minutes=interval_minutes)
    
    return slots


def get_daypart_windows() -> dict[Daypart, TimeWindow]:
    """Get default daypart windows"""
    return {
        Daypart.MORNING: TimeWindow(time(7, 0), time(10, 0)),
        Daypart.EVENING: TimeWindow(time(14, 0), time(21, 0)),
        Daypart.ALLDAY: TimeWindow(time(0, 0), time(23, 59)),
    }


def get_slots(
    target_day: str,  # 'today' or 'tomorrow'
    method: DeliveryMethod,
    now: datetime,
    interval_minutes: int = 15,
    base_buffer_minutes: int = 15,
    tomorrow_cutoff: time = time(23, 0)
) -> Tuple[List[Slot], Optional[str]]:
    """
    Get available slots for a given day and method.
    
    Returns:
        Tuple of (slots list, error message or None)
    """
    # Check tomorrow cutoff
    if target_day == 'tomorrow':
        if now.time() > tomorrow_cutoff:
            return [], "Заказы на завтра принимаются до 23:00"
    
    # Calculate base time for slot generation
    if target_day == 'today':
        base_date = now.date()
    else:
        base_date = now.date() + timedelta(days=1)
    
    # Round now to interval for consistent slot boundaries
    base_time = datetime.combine(base_date, time(0, 0))
    if target_day == 'today':
        base_time = ceil_to_interval(now, interval_minutes)
    
    # Generate slots for MORNING and EVENING windows
    windows = get_daypart_windows()
    all_slots = []
    
    for daypart in [Daypart.MORNING, Daypart.EVENING]:
        window = windows[daypart]
        slots = generate_slots_for_window(
            window, base_time, interval_minutes, base_buffer_minutes
        )
        all_slots.extend(slots)
    
    # Sort by time
    all_slots.sort(key=lambda s: s.time)
    
    return all_slots, None


# ============================================================================
# AVAILABILITY CHECKING
# ============================================================================

def check_availability(
    product_rules: List[AvailabilityRule],
    category_rules: List[AvailabilityRule],
    day: str,  # 'today' or 'tomorrow'
    method: DeliveryMethod,
    now: datetime,
    desired_slot: Optional[time] = None,
    tomorrow_cutoff: time = time(23, 0)
) -> AvailabilityResult:
    """
    Check product availability with full rule hierarchy.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Check tomorrow cutoff
        if day == 'tomorrow' and now.time() > tomorrow_cutoff:
            return AvailabilityResult(
                available=False,
                next_available=None,
                reason_code=UnavailabilityReason.TOMORROW_CUTOFF,
                badge_text="Заказы на завтра до 23:00",
                cta_type="unavailable"
            )
        
        # Sort and filter product rules - filter out None values
        active_product_rules = [
            r for r in product_rules 
            if r is not None and r.is_active and r.allows_method(method)
        ]
        
        # Sort by: is_active (already filtered), method match, daypart match, updated_at desc
        # For now, we use daypart specificity: ALLDAY < MORNING/EVENING
        def rule_priority(r: AvailabilityRule) -> tuple:
            daypart_order = {
                Daypart.MORNING: 0,
                Daypart.EVENING: 0,
                Daypart.ALLDAY: 1
            }
            return (daypart_order.get(r.daypart, 2), r.id)  # Use id as tiebreaker
        
        active_product_rules.sort(key=rule_priority)
        
        # Try product rules first
        applicable_rule = None
        for rule in active_product_rules:
            result = _check_rule_availability(rule, day, method, now, desired_slot)
            if result.reason_code != UnavailabilityReason.METHOD_NOT_ALLOWED:
                applicable_rule = rule
                break
        
        # If no product rule, try category rules
        if not applicable_rule:
            active_cat_rules = [
                r for r in category_rules
                if r is not None and r.is_active and r.allows_method(method)
            ]
            active_cat_rules.sort(key=rule_priority)
            
            for rule in active_cat_rules:
                result = _check_rule_availability(rule, day, method, now, desired_slot)
                if result.reason_code != UnavailabilityReason.METHOD_NOT_ALLOWED:
                    applicable_rule = rule
                    break
        
        # If still no rule, return NO_RULE
        if not applicable_rule:
            return AvailabilityResult(
                available=False,
                next_available=None,
                reason_code=UnavailabilityReason.NO_RULE,
                badge_text="Недоступно",
                cta_type="unavailable"
            )
        
        # Return the check result for the applicable rule
        return _check_rule_availability(applicable_rule, day, method, now, desired_slot)
    
    except Exception as e:
        logger.error(f"CRITICAL ERROR in check_availability: {e}", exc_info=True)
        return AvailabilityResult(
            available=False,
            next_available=None,
            reason_code=UnavailabilityReason.NO_RULE,
            badge_text="Ошибка",
            cta_type="unavailable"
        )


def _check_rule_availability(
    rule: AvailabilityRule,
    day: str,
    method: DeliveryMethod,
    now: datetime,
    desired_slot: Optional[time]
) -> AvailabilityResult:
    """Check availability against a single rule"""
    
    # Check method
    if not rule.allows_method(method):
        return AvailabilityResult(
            available=False,
            next_available=None,
            reason_code=UnavailabilityReason.METHOD_NOT_ALLOWED,
            badge_text=f"Только {', '.join(rule.methods)}",
            cta_type="unavailable"
        )
    
    # Get effective window
    window = rule.get_effective_window()
    
    # Calculate target datetime
    if day == 'today':
        target_date = now.date()
    else:
        target_date = now.date() + timedelta(days=1)
    
    # Determine slot time
    if desired_slot:
        slot_time = desired_slot
    else:
        # For ASAP, use next available slot
        slot_time = window.start
    
    # Check if slot is within window
    if not window.contains(slot_time):
        # Calculate next available slot in window
        next_slot = _calculate_next_available(window, rule.lead_time_minutes, now)
        return AvailabilityResult(
            available=False,
            next_available=next_slot,
            reason_code=UnavailabilityReason.OUTSIDE_WINDOW,
            badge_text="Вне времени работы",
            cta_type="select_time"
        )
    
    # Check lead time (skip if lead_time is 0)
    if rule.lead_time_minutes > 0:
        target_datetime = datetime.combine(target_date, slot_time)
        # Add timezone info to target_datetime to match now (which has timezone)
        if now.tzinfo:
            target_datetime = target_datetime.replace(tzinfo=now.tzinfo)
        min_delivery_time = now + timedelta(minutes=rule.lead_time_minutes)
        
        if target_datetime < min_delivery_time:
            next_available = _calculate_next_available(window, rule.lead_time_minutes, now)
            return AvailabilityResult(
                available=False,
                next_available=next_available,
                reason_code=UnavailabilityReason.LEAD_TIME,
                badge_text=f"Предзаказ за {rule.lead_time_minutes} мин",
                cta_type="preorder"
            )
    
    # All checks passed - available
    return AvailabilityResult(
        available=True,
        next_available=None,
        reason_code=None,
        badge_text="В наличии",
        cta_type="add_to_cart"
    )


def _calculate_next_available(
    window: TimeWindow,
    lead_time_minutes: int,
    now: datetime
) -> datetime:
    """Calculate next available datetime considering lead time"""
    min_time = now + timedelta(minutes=lead_time_minutes)
    
    # Try today first
    today_window_start = datetime.combine(now.date(), window.start)
    today_window_end = datetime.combine(now.date(), window.end)
    
    # Add timezone info if now has timezone
    if now.tzinfo:
        today_window_start = today_window_start.replace(tzinfo=now.tzinfo)
        today_window_end = today_window_end.replace(tzinfo=now.tzinfo)
    
    if min_time <= today_window_end:
        # Available today
        if min_time < today_window_start:
            return today_window_start
        return min_time
    
    # Next available is tomorrow
    tomorrow = now.date() + timedelta(days=1)
    tomorrow_start = datetime.combine(tomorrow, window.start)
    if now.tzinfo:
        tomorrow_start = tomorrow_start.replace(tzinfo=now.tzinfo)
    return tomorrow_start


# ============================================================================
# BADGE TEXT HELPERS
# ============================================================================

def get_reason_display(reason: UnavailabilityReason) -> str:
    """Get human-readable reason text (Russian)"""
    displays = {
        UnavailabilityReason.OUTSIDE_WINDOW: "Вне времени приема заказов",
        UnavailabilityReason.LEAD_TIME: "Требуется предзаказ",
        UnavailabilityReason.METHOD_NOT_ALLOWED: "Недоступно для этого способа",
        UnavailabilityReason.TOMORROW_CUTOFF: "Заказы на завтра до 23:00",
        UnavailabilityReason.INACTIVE: "Временно недоступно",
        UnavailabilityReason.NO_RULE: "Нет правил доступности",
    }
    return displays.get(reason, "Недоступно")


def format_next_available(dt: Optional[datetime]) -> str:
    """Format next available time for display"""
    if not dt:
        return ""
    
    today = datetime.now(dt.tzinfo).date()
    if dt.date() == today:
        return f"Сегодня в {dt.strftime('%H:%M')}"
    else:
        return f"Завтра в {dt.strftime('%H:%M')}"
