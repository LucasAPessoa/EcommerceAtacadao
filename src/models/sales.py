import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, uuid_primary_key
from .enums import DiscountTypeEnum, OrderStatusEnum, StockReservationStatusEnum


def generate_order_code() -> str:
    token = uuid.uuid4().hex.upper()
    return f"PED-{token[:4]}-{token[4:8]}"


if TYPE_CHECKING:
    from .catalog import ProductVariant
    from .identity import User
    from .operations import Refund, Shipment, Transaction


class Coupon(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "coupons"
    id: Mapped[uuid.UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    discount_type: Mapped[DiscountTypeEnum] = mapped_column(SQLEnum(DiscountTypeEnum))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_order_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)


class Cart(Base, TimestampMixin):
    __tablename__ = "carts"
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), unique=True
    )
    user: Mapped["User"] = relationship(back_populates="cart")
    items: Mapped[List["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base, TimestampMixin):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_cart_variant"),
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
    )
    id: Mapped[uuid.UUID] = uuid_primary_key()
    cart_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("carts.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_variants.id")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    cart: Mapped["Cart"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class Order(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "checkout_idempotency_key",
            name="uq_orders_user_checkout_idempotency",
        ),
        CheckConstraint("subtotal_amount >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_orders_discount_non_negative"),
        CheckConstraint("shipping_fee >= 0", name="ck_orders_shipping_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_non_negative"),
    )
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))

    # Índice adicionado para buscas rápidas pelo código
    order_code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, default=generate_order_code
    )

    shipping_address_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    checkout_idempotency_key: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))

    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    discount_type: Mapped[Optional[DiscountTypeEnum]] = mapped_column(SQLEnum(DiscountTypeEnum))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    shipping_provider: Mapped[str] = mapped_column(String(80))
    shipping_service_id: Mapped[Optional[int]] = mapped_column(Integer)
    shipping_service_name: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_delivery_time_days: Mapped[Optional[int]] = mapped_column(Integer)

    status: Mapped[OrderStatusEnum] = mapped_column(
        SQLEnum(OrderStatusEnum), default=OrderStatusEnum.PENDING_PAYMENT
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="order")
    shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="order", uselist=False)
    refunds: Mapped[List["Refund"]] = relationship(back_populates="order")

    # Ligação com a nova tabela de auditoria
    history_logs: Mapped[List["OrderStatusHistory"]] = relationship(back_populates="order")
    stock_reservations: Mapped[List["StockReservation"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "variant_id", name="uq_order_items_order_variant"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price_snapshot >= 0", name="ck_order_items_price_non_negative"),
    )
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orders.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_variants.id")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    base_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    product_name_snapshot: Mapped[str] = mapped_column(String(255))
    variation_name_snapshot: Mapped[str] = mapped_column(String(100))
    sku_snapshot: Mapped[str] = mapped_column(String(100))
    pricing_tier_min_quantity: Mapped[Optional[int]] = mapped_column(Integer)
    logistics_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB)

    order: Mapped["Order"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class StockReservation(Base, TimestampMixin):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        UniqueConstraint("order_id", "variant_id", name="uq_stock_reservations_order_variant"),
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_variants.id"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[StockReservationStatusEnum] = mapped_column(
        SQLEnum(StockReservationStatusEnum), default=StockReservationStatusEnum.ACTIVE, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    order: Mapped["Order"] = relationship(back_populates="stock_reservations")
    variant: Mapped["ProductVariant"] = relationship()


# NOVA TABELA DE AUDITORIA
class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orders.id"))
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    old_status: Mapped[Optional[OrderStatusEnum]] = mapped_column(
        SQLEnum(OrderStatusEnum), nullable=True
    )
    new_status: Mapped[OrderStatusEnum] = mapped_column(SQLEnum(OrderStatusEnum))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    order: Mapped["Order"] = relationship(back_populates="history_logs")
