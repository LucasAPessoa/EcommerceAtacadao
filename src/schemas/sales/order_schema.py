from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.models.enums import DiscountTypeEnum, OrderStatusEnum, PaymentMethodEnum
from src.schemas.base_schema import TimestampMixinSchema
from src.schemas.catalog.product_variant_schema import ProductVariantResponseSchema


class OrderItemCreateSchema(BaseModel):
    variant_id: UUID
    quantity: int = Field(gt=0)


class OrderItemUpdateSchema(BaseModel):
    quantity: int = Field(gt=0)


class OrderAddressUpdateSchema(BaseModel):
    address_id: UUID


class OrderCreateSchema(BaseModel):
    items: List[OrderItemCreateSchema] = Field(min_length=1)
    address_id: UUID
    payment_method: PaymentMethodEnum
    installments: int = Field(1, ge=1)
    coupon_code: Optional[str] = None


class OrderItemResponseSchema(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    unit_price_snapshot: float
    variant: ProductVariantResponseSchema

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.unit_price_snapshot * self.quantity, 2)


class OrderResponseSchema(TimestampMixinSchema):
    id: UUID
    order_code: str
    user_id: UUID
    status: OrderStatusEnum
    shipping_address_snapshot: dict
    coupon_code: Optional[str] = None
    discount_type: Optional[DiscountTypeEnum] = None
    discount_amount: float
    shipping_fee: float
    total_amount: float
    items: List[OrderItemResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def items_subtotal(self) -> float:
        return round(sum(item.subtotal for item in self.items), 2)
