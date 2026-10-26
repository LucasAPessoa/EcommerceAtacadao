"""Schemas do portal admin para pedidos (contracts/http-api.md, seção Pedidos)."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.models.enums import (
    OrderStatusEnum,
    PaymentMethodEnum,
    ReconciliationOutcomeEnum,
    ReconciliationReasonEnum,
    ReconciliationStatusEnum,
    TransactionStatusEnum,
)
from src.schemas.admin.products import Money


class OrderAction(str, Enum):
    CANCEL = "cancel"
    RECONCILE = "reconcile"
    REQUEST_REFUND = "request_refund"


class AdminOrderCustomer(BaseModel):
    id: UUID
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrderListItem(BaseModel):
    id: UUID
    order_code: str
    status: OrderStatusEnum
    created_at: datetime
    total_amount: Money
    items_count: int
    customer: AdminOrderCustomer


class AdminOrderItem(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    unit_price_snapshot: Money
    base_price_snapshot: Money
    product_name_snapshot: str
    variation_name_snapshot: str
    sku_snapshot: str
    pricing_tier_min_quantity: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> Money:
        return self.unit_price_snapshot * self.quantity


class AdminOrderTransaction(BaseModel):
    id: UUID
    payment_method: PaymentMethodEnum
    gateway_provider: str
    amount: Money
    installments: int
    status: TransactionStatusEnum
    gateway_status_detail: Optional[str] = None
    paid_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AdminOrderReconciliation(BaseModel):
    status: ReconciliationStatusEnum
    reason: ReconciliationReasonEnum
    outcome: Optional[ReconciliationOutcomeEnum] = None

    model_config = ConfigDict(from_attributes=True)


class AdminOrderStatusChange(BaseModel):
    old_status: Optional[OrderStatusEnum] = None
    new_status: OrderStatusEnum
    created_at: datetime
    changed_by: Optional[str] = None


class AdminOrderDetail(BaseModel):
    id: UUID
    order_code: str
    status: OrderStatusEnum
    created_at: datetime
    updated_at: datetime
    customer: AdminOrderCustomer
    items: list[AdminOrderItem] = Field(default_factory=list)
    subtotal_amount: Money
    discount_amount: Money
    coupon_code: Optional[str] = None
    shipping_fee: Money
    total_amount: Money
    currency: str
    shipping_provider: str
    shipping_service_name: Optional[str] = None
    shipping_delivery_time_days: Optional[int] = None
    shipping_address_snapshot: dict[str, Any]
    transactions: list[AdminOrderTransaction] = Field(default_factory=list)
    reconciliation: Optional[AdminOrderReconciliation] = None
    status_history: list[AdminOrderStatusChange] = Field(default_factory=list)
    allowed_actions: list[OrderAction] = Field(default_factory=list)
