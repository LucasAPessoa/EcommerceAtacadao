import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, Numeric, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, uuid_primary_key
from .enums import OrderStatusEnum, DiscountTypeEnum

def generate_order_code() -> str:
    token = uuid.uuid4().hex.upper()
    return f"PED-{token[:4]}-{token[4:8]}"

if TYPE_CHECKING:
    from .catalog import ProductVariant
    from .identity import User
    from .operations import Transaction, Refund, Shipment

class Coupon(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'coupons'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    discount_type: Mapped[DiscountTypeEnum] = mapped_column(SQLEnum(DiscountTypeEnum))
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2))
    min_order_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)

class Cart(Base, TimestampMixin):
    __tablename__ = 'carts'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'), unique=True)
    user: Mapped["User"] = relationship(back_populates="cart")
    items: Mapped[List["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")

class CartItem(Base, TimestampMixin):
    __tablename__ = 'cart_items'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    cart_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('carts.id'))
    variant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('product_variants.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    cart: Mapped["Cart"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()

class Order(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'orders'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'))
    
    # Índice adicionado para buscas rápidas pelo código
    order_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, default=generate_order_code)
    
    shipping_address_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    discount_type: Mapped[Optional[DiscountTypeEnum]] = mapped_column(SQLEnum(DiscountTypeEnum))
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    shipping_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    
    status: Mapped[OrderStatusEnum] = mapped_column(SQLEnum(OrderStatusEnum), default=OrderStatusEnum.PENDING)
    
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="order")
    shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="order", uselist=False)
    refunds: Mapped[List["Refund"]] = relationship(back_populates="order")
    
    # Ligação com a nova tabela de auditoria
    history_logs: Mapped[List["OrderStatusHistory"]] = relationship(back_populates="order")

class OrderItem(Base, TimestampMixin):
    __tablename__ = 'order_items'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id'))
    variant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('product_variants.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_snapshot: Mapped[float] = mapped_column(Numeric(10, 2))
    
    order: Mapped["Order"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()

# NOVA TABELA DE AUDITORIA
class OrderStatusHistory(Base):
    __tablename__ = 'order_status_history'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id'))
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    old_status: Mapped[Optional[OrderStatusEnum]] = mapped_column(SQLEnum(OrderStatusEnum), nullable=True)
    new_status: Mapped[OrderStatusEnum] = mapped_column(SQLEnum(OrderStatusEnum))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    order: Mapped["Order"] = relationship(back_populates="history_logs")