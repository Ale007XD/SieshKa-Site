"""
Unit tests for timefirst_core module.
Run with: pytest tests/test_timefirst_core.py -v
"""

import pytest
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.timefirst_core import (
    Daypart,
    DeliveryMethod,
    UnavailabilityReason,
    AvailabilityRule,
    TimeWindow,
    ceil_to_interval,
    generate_slots_for_window,
    get_slots,
    check_availability,
    get_reason_display,
    format_next_available,
)


# Test fixtures
@pytest.fixture
def tz():
    """Test timezone"""
    return ZoneInfo("Asia/Ho_Chi_Minh")


@pytest.fixture
def morning_rule():
    """Morning availability rule"""
    return AvailabilityRule(
        id=1,
        scope_type="product",
        scope_id=1,
        daypart=Daypart.MORNING,
        lead_time_minutes=0,
        methods=["delivery", "pickup"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )


@pytest.fixture
def evening_rule():
    """Evening availability rule"""
    return AvailabilityRule(
        id=2,
        scope_type="product",
        scope_id=2,
        daypart=Daypart.EVENING,
        lead_time_minutes=0,
        methods=["delivery", "pickup"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )


@pytest.fixture
def preorder_rule():
    """Pre-order rule with 180 min lead time"""
    return AvailabilityRule(
        id=3,
        scope_type="product",
        scope_id=3,
        daypart=Daypart.ALLDAY,
        lead_time_minutes=180,
        methods=["delivery", "pickup"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )


@pytest.fixture
def delivery_only_rule():
    """Delivery-only rule"""
    return AvailabilityRule(
        id=4,
        scope_type="product",
        scope_id=4,
        daypart=Daypart.ALLDAY,
        lead_time_minutes=0,
        methods=["delivery"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )


# ============================================================================
# TEST 1: 08:00 today breakfast ok
# ============================================================================
def test_08_00_morning_available(tz, morning_rule):
    """08:00 today - breakfast should be available"""
    now = datetime(2026, 2, 15, 8, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[morning_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    assert result.available is True
    assert result.reason_code is None
    assert result.cta_type == "add_to_cart"


# ============================================================================
# TEST 2: 11:00 today breakfast not ok -> next tomorrow 07:00
# ============================================================================
def test_11_00_morning_unavailable_next_tomorrow(tz, morning_rule):
    """11:00 today - breakfast not available, next is tomorrow morning"""
    now = datetime(2026, 2, 15, 11, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[morning_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    assert result.available is False
    assert result.reason_code == UnavailabilityReason.OUTSIDE_WINDOW
    assert result.next_available is not None
    # Next available should be tomorrow morning
    assert result.next_available.date() == now.date() + timedelta(days=1)


# ============================================================================
# TEST 3: 13:00 today fastfood -> next 14:00 (evening start)
# ============================================================================
def test_13_00_fastfood_evening_available(tz, evening_rule):
    """13:00 today - fastfood available in evening from 14:00"""
    now = datetime(2026, 2, 15, 13, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[evening_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    # At 13:00, evening window hasn't started yet
    assert result.available is False
    assert result.reason_code == UnavailabilityReason.OUTSIDE_WINDOW
    assert result.next_available is not None
    # Next available is 14:00 today
    assert result.next_available.time() == time(14, 0)


# ============================================================================
# TEST 4: 20:00 today preorder lead 180 -> next tomorrow morning/evening
# ============================================================================
def test_20_00_preorder_lead_time_180(tz, preorder_rule):
    """20:00 today - preorder with 180 min lead time -> tomorrow"""
    now = datetime(2026, 2, 15, 20, 0, tzinfo=tz)

    # Desired slot is now + small buffer, but need 180 min lead time
    result = check_availability(
        product_rules=[preorder_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=time(20, 30),
    )

    # 20:30 is less than 180 min from 20:00
    assert result.available is False
    assert result.reason_code == UnavailabilityReason.LEAD_TIME
    assert result.next_available is not None


# ============================================================================
# TEST 5: 22:30 today schedule tomorrow ok
# ============================================================================
def test_22_30_tomorrow_order_ok(tz, evening_rule):
    """22:30 today - can order for tomorrow before 23:00 cutoff"""
    now = datetime(2026, 2, 15, 22, 30, tzinfo=tz)

    result = check_availability(
        product_rules=[evening_rule],
        category_rules=[],
        day="tomorrow",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=time(15, 0),
    )

    assert result.available is True
    assert result.reason_code is None
    assert result.cta_type == "add_to_cart"


# ============================================================================
# TEST 6: 23:30 today schedule tomorrow blocked (TOMORROW_CUTOFF)
# ============================================================================
def test_23_30_tomorrow_blocked_cutoff(tz, evening_rule):
    """23:30 today - cannot order for tomorrow after 23:00 cutoff"""
    now = datetime(2026, 2, 15, 23, 30, tzinfo=tz)

    result = check_availability(
        product_rules=[evening_rule],
        category_rules=[],
        day="tomorrow",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    assert result.available is False
    assert result.reason_code == UnavailabilityReason.TOMORROW_CUTOFF
    assert result.cta_type == "unavailable"


# ============================================================================
# TEST 7: method not allowed (pickup only product)
# ============================================================================
def test_method_not_allowed(tz):
    """Pickup-only product should not be available for delivery"""
    pickup_only_rule = AvailabilityRule(
        id=5,
        scope_type="product",
        scope_id=5,
        daypart=Daypart.ALLDAY,
        lead_time_minutes=0,
        methods=["pickup"],  # Only pickup
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )

    now = datetime(2026, 2, 15, 12, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[pickup_only_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,  # Requesting delivery
        now=now,
        desired_slot=None,
    )

    assert result.available is False
    assert result.reason_code == UnavailabilityReason.METHOD_NOT_ALLOWED


# ============================================================================
# TEST 8: inactive product
# ============================================================================
def test_inactive_product(tz, morning_rule):
    """Inactive product should not be available"""
    inactive_rule = AvailabilityRule(
        id=6,
        scope_type="product",
        scope_id=6,
        daypart=Daypart.MORNING,
        lead_time_minutes=0,
        methods=["delivery"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=False,  # Inactive!
    )

    now = datetime(2026, 2, 15, 8, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[inactive_rule],
        category_rules=[],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    # No active rules, should be NO_RULE
    assert result.available is False
    assert result.reason_code == UnavailabilityReason.NO_RULE


# ============================================================================
# TEST 9: Category rule fallback when no product rule
# ============================================================================
def test_category_rule_fallback(tz):
    """When no product rule, use category rule"""
    category_rule = AvailabilityRule(
        id=7,
        scope_type="category",
        scope_id=1,
        daypart=Daypart.MORNING,
        lead_time_minutes=0,
        methods=["delivery"],
        allow_tomorrow=True,
        tomorrow_cutoff=time(23, 0),
        is_active=True,
    )

    now = datetime(2026, 2, 15, 8, 0, tzinfo=tz)

    result = check_availability(
        product_rules=[],  # No product rules
        category_rules=[category_rule],
        day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        desired_slot=None,
    )

    assert result.available is True
    assert result.reason_code is None


# ============================================================================
# TEST 10: Slot generation with 15-minute interval
# ============================================================================
def test_slot_generation_interval(tz):
    """Test slot generation creates correct intervals"""
    window = TimeWindow(start=time(14, 0), end=time(15, 0))
    base_time = datetime(2026, 2, 15, 13, 0, tzinfo=tz)

    slots = generate_slots_for_window(
        window=window, base_time=base_time, interval_minutes=15, base_buffer_minutes=15
    )

    # Should have slots: 14:00, 14:15, 14:30, 14:45, 15:00
    assert len(slots) == 5
    assert slots[0].time == time(14, 0)
    assert slots[1].time == time(14, 15)
    assert slots[4].time == time(15, 0)


# ============================================================================
# TEST 11: Ceil to interval function
# ============================================================================
def test_ceil_to_interval():
    """Test rounding up to interval"""
    tz = ZoneInfo("Asia/Ho_Chi_Minh")

    # 08:07 should ceil to 08:15
    dt = datetime(2026, 2, 15, 8, 7, tzinfo=tz)
    result = ceil_to_interval(dt, 15)
    assert result == datetime(2026, 2, 15, 8, 15, tzinfo=tz)

    # 08:15 should stay 08:15
    dt = datetime(2026, 2, 15, 8, 15, tzinfo=tz)
    result = ceil_to_interval(dt, 15)
    assert result == datetime(2026, 2, 15, 8, 15, tzinfo=tz)

    # 08:16 should ceil to 08:30
    dt = datetime(2026, 2, 15, 8, 16, tzinfo=tz)
    result = ceil_to_interval(dt, 15)
    assert result == datetime(2026, 2, 15, 8, 30, tzinfo=tz)


# ============================================================================
# TEST 12: Reason display text
# ============================================================================
def test_reason_display_text():
    """Test reason code display text"""
    assert "Вне времени" in get_reason_display(UnavailabilityReason.OUTSIDE_WINDOW)
    assert "предзаказ" in get_reason_display(UnavailabilityReason.LEAD_TIME)
    assert "23:00" in get_reason_display(UnavailabilityReason.TOMORROW_CUTOFF)


# ============================================================================
# TEST 13: Format next available
# ============================================================================
def test_format_next_available(tz):
    """Test formatting of next available time"""
    today = datetime.now(tz).date()

    # Today
    dt = datetime.combine(today, time(14, 30)).replace(tzinfo=tz)
    text = format_next_available(dt)
    assert "Сегодня" in text
    assert "14:30" in text

    # Tomorrow
    tomorrow = today + timedelta(days=1)
    dt = datetime.combine(tomorrow, time(9, 0)).replace(tzinfo=tz)
    text = format_next_available(dt)
    assert "Завтра" in text
    assert "09:00" in text


# ============================================================================
# TEST 14: Get slots for today
# ============================================================================
def test_get_slots_today(tz):
    """Test slot generation for today"""
    now = datetime(2026, 2, 15, 10, 0, tzinfo=tz)

    slots, error = get_slots(
        target_day="today",
        method=DeliveryMethod.DELIVERY,
        now=now,
        interval_minutes=60,  # 1 hour for simpler test
        base_buffer_minutes=30,
    )

    assert error is None
    assert len(slots) > 0
    # First slot should be >= 10:30 (now + buffer)
    first_slot_time = datetime.combine(now.date(), slots[0].time)
    min_allowed = now + timedelta(minutes=30)
    assert first_slot_time >= min_allowed.replace(tzinfo=None)


# ============================================================================
# TEST 15: Get slots for tomorrow after cutoff
# ============================================================================
def test_get_slots_tomorrow_after_cutoff(tz):
    """Test slot generation blocked after 23:00 cutoff"""
    now = datetime(2026, 2, 15, 23, 30, tzinfo=tz)

    slots, error = get_slots(
        target_day="tomorrow",
        method=DeliveryMethod.DELIVERY,
        now=now,
        tomorrow_cutoff=time(23, 0),
    )

    assert error is not None
    assert "23:00" in error
    assert len(slots) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
