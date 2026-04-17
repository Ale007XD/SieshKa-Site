from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date
import re

class OrderItemIn(BaseModel):
    product_id: int = Field(..., gt=0)
    qty: int = Field(..., gt=0, le=20)

class OrderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=5, max_length=20)
    address: str = Field(..., min_length=8, max_length=300)
    comment: Optional[str] = Field(None, max_length=500)
    delivery_mode: str = Field(default="asap", pattern="^(asap|slot)$")
    delivery_slot: Optional[str] = Field(
        None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    )
    delivery_date: Optional[date] = None
    payment_method: str = Field(
        default="cash", pattern="^(cash|sbp_transfer|yookassa_card)$"
    )
    items: List[OrderItemIn]
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=64)
    csrf_token: Optional[str] = Field(None, min_length=32, max_length=128)
    client_max_uid: Optional[int] = Field(None, gt=0)
    zone_id: Optional[int] = Field(None, gt=0, description="ID зоны доставки")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v):
        v = re.sub(r"[<>{}/\\]", "", v)
        v = " ".join(v.split())
        return v.strip()

    @field_validator("address")
    @classmethod
    def sanitize_address(cls, v):
        v = re.sub(r"[<>{}/\\]", "", v)
        v = " ".join(v.split())
        return v.strip()

    @field_validator("comment")
    @classmethod
    def sanitize_comment(cls, v):
        if not v:
            return v
        v = re.sub(r"[<>{}/\\]", "", v)
        v = " ".join(v.split())
        return v.strip() if v else None

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        if not v:
            raise ValueError("Cart is empty")
        if len(v) > 50:
            raise ValueError("Too many items (max 50)")
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate items in cart")
        return v

    @field_validator("delivery_slot")
    @classmethod
    def validate_delivery_slot(cls, v, info):
        delivery_mode = info.data.get("delivery_mode")
        if delivery_mode == "slot" and not v:
            raise ValueError("Delivery slot is required when delivery_mode is 'slot'")
        if delivery_mode == "asap" and v:
            raise ValueError(
                "Delivery slot should not be provided when delivery_mode is 'asap'"
            )
        return v

    @field_validator("delivery_date")
    @classmethod
    def validate_delivery_date(cls, v, info):
        delivery_mode = info.data.get("delivery_mode")
        if delivery_mode == "slot":
            if not v:
                raise ValueError("Delivery date is required for slot delivery")
            if v < date.today():
                raise ValueError("Delivery date cannot be in the past")
        return v

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: Optional[str] = None
    timestamp: str

class DeliverySlotResponse(BaseModel):
    slot_time: str
    max_orders: int
    current_orders: int
    available: bool

class DeliverySlotsAvailability(BaseModel):
    date: date
    slots: List[DeliverySlotResponse]
