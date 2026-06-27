from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from .base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from .catalog import ProductVariant
    from .identity import User
    from .operations import Transaction, Refund, Shipment

class Coupon(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'coupons'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_type: Mapped[str] = mapped_column(String(20)) # PERCENTAGE, FIXED_AMOUNT, FREE_SHIPPING
    discount_value: Mapped[float] = mapped_column(Float)
    min_order_amount: Mapped[Optional[float]] = mapped_column(Float)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)

class Cart(Base, TimestampMixin):
    __tablename__ = 'carts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    
    user: Mapped["User"] = relationship(back_populates="cart")
    items: Mapped[List["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")

class CartItem(Base, TimestampMixin):
    __tablename__ = 'cart_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey('carts.id'))
    variant_id: Mapped[int] = mapped_column(ForeignKey('product_variants.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    
    cart: Mapped["Cart"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()

class Order(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    
    # Snapshot de endereço em JSONB
    shipping_address_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    discount_type: Mapped[Optional[str]] = mapped_column(String(20))
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_fee: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float)
    
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="order")
    shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="order", uselist=False)
    refunds: Mapped[List["Refund"]] = relationship(back_populates="order")

class OrderItem(Base, TimestampMixin):
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    variant_id: Mapped[int] = mapped_column(ForeignKey('product_variants.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_snapshot: Mapped[float] = mapped_column(Float)
    
    order: Mapped["Order"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()