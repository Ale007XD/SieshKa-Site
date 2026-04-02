import enum
from typing import Optional  # ← ДОБАВИЛИ
from datetime import datetime, date, timezone
from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, Enum, Date
)
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
    menu_period: Mapped[MenuPeriod] = mapped_column(Enum(MenuPeriod), default=MenuPeriod.both, index=True)
    
    # Self-referential relationship for subcategories
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    
    # Relationships
    products: Mapped[list["Product"]] = relationship(back_populates="category")
    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")

    def __repr__(self) -> str:
        return self.name
    
    def get_all_products(self) -> list["Product"]:
        """Recursively get all products from category and its subcategories"""
        products = [p for p in self.products if p.is_active]
        for child in self.children:
            if child.is_active:
                products.extend(child.get_all_products())
        return products
    
    def get_hierarchy_path(self) -> str:
        """Get full path like 'Parent > Child > Subchild'"""
        if self.parent:
            return f"{self.parent.get_hierarchy_path()} > {self.name}"
        return self.name
    
    def is_leaf_category(self) -> bool:
        """Check if category has no subcategories"""
        return len(self.children) == 0

class Product(Base):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"),
