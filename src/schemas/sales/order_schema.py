from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.models.enums import (
    DiscountTypeEnum,
    OrderStatusEnum,
    PaymentMethodEnum,
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


class OrderResponseSchema(TimestampMixinSchema):
    id: UUID
    order_code: str
    user_id: UUID
    status: OrderStatusEnum
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
