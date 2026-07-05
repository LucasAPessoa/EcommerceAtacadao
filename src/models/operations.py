import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import DateTime, Numeric, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, uuid_primary_key
from .enums import PaymentMethodEnum, TransactionStatusEnum, RefundStatusEnum, ShipmentStatusEnum

if TYPE_CHECKING:
    from .sales import Order

class Transaction(Base, TimestampMixin):
    __tablename__ = 'transactions'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id'))
    
    payment_method: Mapped[PaymentMethodEnum] = mapped_column(SQLEnum(PaymentMethodEnum))
    gateway_ref_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    installments: Mapped[int] = mapped_column(Integer, default=1)
    gateway_fee: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    
    status: Mapped[TransactionStatusEnum] = mapped_column(SQLEnum(TransactionStatusEnum), default=TransactionStatusEnum.PENDING)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="transactions")

class Refund(Base, TimestampMixin):
    __tablename__ = 'refunds'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id'))
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey('transactions.id'))
    
    amount_refunded: Mapped[float] = mapped_column(Numeric(10, 2))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[RefundStatusEnum] = mapped_column(SQLEnum(RefundStatusEnum), default=RefundStatusEnum.REQUESTED)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="refunds")

class LocalCEPRange(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'local_cep_ranges'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    cep_start: Mapped[str] = mapped_column(String(10), index=True)
    cep_end: Mapped[str] = mapped_column(String(10), index=True)
    neighborhood: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_rate: Mapped[float] = mapped_column(Numeric(10, 2))

class Shipment(Base, TimestampMixin):
    __tablename__ = 'shipments'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id'), unique=True)
    local_cep_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey('local_cep_ranges.id'))
    
    provider: Mapped[str] = mapped_column(String(50))
    tracking_code: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    shipping_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    
    status: Mapped[ShipmentStatusEnum] = mapped_column(SQLEnum(ShipmentStatusEnum), default=ShipmentStatusEnum.PREPARING)
    
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="shipment")

class ERPWebhookLog(Base, TimestampMixin):
    __tablename__ = 'erp_webhook_logs'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    related_sku: Mapped[Optional[str]] = mapped_column(String(100), index=True)