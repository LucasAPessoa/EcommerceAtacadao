from typing import Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, Column
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from .base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from .sales import Order

class Transaction(Base, TimestampMixin):
    __tablename__ = 'transactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    payment_method: Mapped[str] = mapped_column(String(50)) # PIX, CREDIT_CARD
    gateway_ref_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    amount: Mapped[float] = mapped_column(Float)
    installments: Mapped[int] = mapped_column(Integer, default=1)
    gateway_fee: Mapped[Optional[float]] = mapped_column(Float)
    
    status: Mapped[str] = mapped_column(String(50))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="transactions")

class Refund(Base, TimestampMixin):
    """Gestão de Devoluções/Cancelamentos (CDC)"""
    __tablename__ = 'refunds'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    transaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey('transactions.id'))
    
    amount_refunded: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="REQUESTED")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="refunds")

class LocalCEPRange(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'local_cep_ranges'
    id: Mapped[int] = mapped_column(primary_key=True)
    cep_start: Mapped[str] = mapped_column(String(10))
    cep_end: Mapped[str] = mapped_column(String(10))
    neighborhood: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_rate: Mapped[float] = mapped_column(Float)

class Shipment(Base, TimestampMixin):
    __tablename__ = 'shipments'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    local_cep_id: Mapped[Optional[int]] = mapped_column(ForeignKey('local_cep_ranges.id'))
    
    provider: Mapped[str] = mapped_column(String(50))
    tracking_code: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_cost: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="PREPARING")
    
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    order: Mapped["Order"] = relationship(back_populates="shipment")

class ERPWebhookLog(Base, TimestampMixin):
    """Log otimizado com JSONB para facilitar buscas e rastreabilidade"""
    __tablename__ = 'erp_webhook_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    related_sku: Mapped[Optional[str]] = mapped_column(String(100))