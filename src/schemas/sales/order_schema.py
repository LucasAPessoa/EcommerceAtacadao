from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.models.enums import (
    DiscountTypeEnum,
    OrderStatusEnum,
    PaymentMethodEnum,
    ReconciliationOutcomeEnum,
    ReconciliationReasonEnum,
    ReconciliationStatusEnum,
    RefundStatusEnum,
    TransactionStatusEnum,
)
from src.schemas.base_schema import TimestampMixinSchema
from src.schemas.catalog.product_variant_schema import ProductVariantResponseSchema


class OrderItemResponseSchema(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    unit_price_snapshot: Decimal
    base_price_snapshot: Decimal
    product_name_snapshot: str
    variation_name_snapshot: str
    sku_snapshot: str
    pricing_tier_min_quantity: Optional[int] = None
    logistics_snapshot: Dict[str, Any]
    variant: ProductVariantResponseSchema

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> Decimal:
        return self.unit_price_snapshot * self.quantity


class OrderTransactionResponseSchema(BaseModel):
    id: UUID
    payment_method: PaymentMethodEnum
    amount: Decimal
    installments: int
    status: TransactionStatusEnum
    gateway_ref_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    gateway_provider: str
    checkout_url: Optional[str] = None
    gateway_status_detail: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OrderReconciliationResponseSchema(BaseModel):
    id: UUID
    order_id: UUID
    status: ReconciliationStatusEnum
    reason: ReconciliationReasonEnum
    outcome: Optional[ReconciliationOutcomeEnum] = None
    next_poll_after_seconds: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OrderReconciliationQueueResponseSchema(OrderReconciliationResponseSchema):
    refund_status: Optional[RefundStatusEnum] = None
    refund_attempts: Optional[int] = None
    refund_last_attempt_at: Optional[datetime] = None
    refund_next_retry_at: Optional[datetime] = None
    refund_last_error_code: Optional[str] = None


class OrderResponseSchema(TimestampMixinSchema):
    id: UUID
    order_code: str
    user_id: UUID
    status: OrderStatusEnum
    reconciliation: Optional[OrderReconciliationResponseSchema] = Field(
        default=None, validation_alias="payment_reconciliation"
    )
    shipping_address_snapshot: dict
    checkout_idempotency_key: Optional[UUID] = None
    coupon_code: Optional[str] = None
    discount_type: Optional[DiscountTypeEnum] = None
    subtotal_amount: Decimal
    discount_amount: Decimal
    shipping_fee: Decimal
    total_amount: Decimal
    currency: str
    shipping_provider: str
    shipping_service_id: Optional[int] = None
    shipping_service_name: Optional[str] = None
    shipping_delivery_time_days: Optional[int] = None
    items: List[OrderItemResponseSchema] = Field(default_factory=list)
    transactions: List[OrderTransactionResponseSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def items_subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def payment_status(self) -> Optional[TransactionStatusEnum]:
        return self.transactions[0].status if self.transactions else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fulfillment_status(self) -> OrderStatusEnum:
        return self.status
