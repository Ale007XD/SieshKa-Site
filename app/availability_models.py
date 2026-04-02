"""
Availability Rules Models for Time-First Menu System
"""
import enum
from datetime import datetime, time, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, Enum, Time, ARRAY, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from .timefirst_core import Daypart, DeliveryMethod, UnavailabilityReason


class AvailabilityScopeType(str, enum.Enum):
    """Scope type for availability rules - must match DB enum values exactly"""
    product = "product"
    category = "category"


class AvailabilityRule(Base):
    """
    Availability rules for products and categories.
    
    Rules define when and how products can be ordered:
    - Daypart: MORNING (07-10), EVENING (14-21), or ALLDAY
    - Lead time: minimum time before delivery (e.g., 180 min for pre-order items)
    - Methods: delivery and/or pickup
    - Tomorrow cutoff: latest time to order for tomorrow (default 23:00)
    """
    __tablename__ = "availability_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Scope: product or category
    scope_type: Mapped[AvailabilityScopeType] = mapped_column(
        Enum(AvailabilityScopeType), 
        nullable=False,
        index=True
    )
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Daypart configuration
    daypart: Mapped[Daypart] = mapped_column(
        Enum(Daypart), 
        default=Daypart.ALLDAY,
        nullable=False
    )
    
    # Optional explicit time window (if null, uses daypart defaults)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    
    # Lead time in minutes (for pre-order items)
    lead_time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Allowed methods (PostgreSQL array of enums)
    # Note: SQLAlchemy 2.x Mapped classes don't support default_factory
    # Using default=list is acceptable here as we're not mutating the default
    methods: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=list,
        nullable=False
    )
    
    # Tomorrow ordering configuration
    allow_tomorrow: Mapped[bool] = mapped_column(Boolean, default=True)
    tomorrow_cutoff: Mapped[time] = mapped_column(
        Time, 
        default=time(23, 0)  # 23:00
    )
    
    # Timezone for this rule
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Irkutsk")
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Metadata
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=func.now(),
        onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<AvailabilityRule {self.scope_type}:{self.scope_id} {self.daypart}>"
    
    def allows_method(self, method: DeliveryMethod) -> bool:
        """Check if this rule allows the given delivery method"""
        return method.value in self.methods
    
    def get_effective_time_window(self) -> tuple[time, time]:
        """Get effective start/end times based on daypart or explicit settings"""
        if self.start_time and self.end_time:
            return (self.start_time, self.end_time)
        
        # Default windows based on daypart
        if self.daypart == Daypart.MORNING:
            return (time(7, 0), time(10, 0))
        elif self.daypart == Daypart.EVENING:
            return (time(14, 0), time(21, 0))
        else:  # ALLDAY
            return (time(0, 0), time(23, 59))


class CartDraft(Base):
    """
    Draft cart stored in Redis (backup in DB for persistence).
    Used for complex multi-slot orders and "cart for tomorrow" feature.
    """
    __tablename__ = "cart_drafts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Unique cart identifier (session-based)
    cart_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # Customer info (optional at draft stage)
    customer_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone_e164: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Cart configuration
    target_day: Mapped[str] = mapped_column(String(10))  # "today" or "tomorrow"
    delivery_method: Mapped[str] = mapped_column(String(20))  # "delivery" or "pickup"
    selected_slot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Items as JSON
    items_json: Mapped[str] = mapped_column(Text)
    
    # Totals
    total_rub: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    
    def __repr__(self) -> str:
        return f"<CartDraft {self.cart_key} {self.target_day}>"


class MenuConfiguration(Base):
    """
    Global menu configuration and feature flags.
    """
    __tablename__ = "menu_configuration"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Business timezone
    business_tz: Mapped[str] = mapped_column(String(50), default="Asia/Irkutsk")
    
    # Daypart windows (can override defaults)
    morning_start: Mapped[time] = mapped_column(Time, default=time(7, 0))
    morning_end: Mapped[time] = mapped_column(Time, default=time(10, 0))
    evening_start: Mapped[time] = mapped_column(Time, default=time(14, 0))
    evening_end: Mapped[time] = mapped_column(Time, default=time(21, 0))
    
    # Default slot generation
    slot_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    base_buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    
    # Feature flags
    enable_tomorrow_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    tomorrow_order_cutoff: Mapped[time] = mapped_column(Time, default=time(23, 0))
    
    # Allowed delivery methods in UI: "both", "delivery", "pickup"
    allowed_methods: Mapped[str] = mapped_column(String(20), default="both")
    
    # Cache versioning for cache invalidation
    menu_version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Delivery fee (fixed amount in rubles)
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc)
    )
    
    def __repr__(self) -> str:
        return f"<MenuConfiguration v{self.menu_version}>"
