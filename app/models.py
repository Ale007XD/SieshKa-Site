import enum
from datetime import datetime, date, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, Enum, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class OrderStatus(str, enum.Enum):
    new = "new"
    accepted = "accepted"
    cooking = "cooking"
    on_the_way = "on_the_way"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    sbp_transfer = "sbp_transfer"
    yookassa_card = "yookassa_card"


class DeliveryMode(str, enum.Enum):
    asap = "asap"
    slot = "slot"


class MenuPeriod(str, enum.Enum):
    morning = "morning"
    evening = "evening"
    both = "both"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    sort: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    menu_period: Mapped[MenuPeriod] = mapped_column(
        Enum(MenuPeriod), default=MenuPeriod.both, index=True
    )

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category")
    parent: Mapped["Category | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")

    def __repr__(self) -> str:
        return self.name

    def get_all_products(self) -> list["Product"]:
        products = [p for p in self.products if p.is_active]
        for child in self.children:
            if child.is_active:
                products.extend(child.get_all_products())
        return products

    def get_hierarchy_path(self) -> str:
        if self.parent:
            return f"{self.parent.get_hierarchy_path()} > {self.name}"
        return self.name

    def is_leaf_category(self) -> bool:
        return len(self.children) == 0


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_rub: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    menu_period_override: Mapped[MenuPeriod | None] = mapped_column(
        Enum(MenuPeriod), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, onupdate=datetime.now(timezone.utc), nullable=True
    )

    category: Mapped["Category"] = relationship(back_populates="products")


class DeliverySlot(Base):
    __tablename__ = "delivery_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot_time: Mapped[str] = mapped_column(String(20), unique=True)
    max_orders: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )


class DeliveryZone(Base):
    __tablename__ = "delivery_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    delivery_time_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str] = mapped_column(String(32), index=True)
    address: Mapped[str] = mapped_column(String(300))
    comment: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    delivery_fee_rub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_rub: Mapped[int] = mapped_column(Integer)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.new
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), default=PaymentMethod.cash
    )
    payment_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    yookassa_payment_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    yookassa_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_message_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_max_uid: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    delivery_mode: Mapped[DeliveryMode] = mapped_column(
        Enum(DeliveryMode), default=DeliveryMode.asap
    )
    delivery_slot: Mapped[str | None] = mapped_column(String(20), index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # FK for Delivery Zone
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    name_snapshot: Mapped[str] = mapped_column(String(200))
    price_rub_snapshot: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)

    order: Mapped["Order"] = relationship(back_populates="items")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc), index=True
    )
