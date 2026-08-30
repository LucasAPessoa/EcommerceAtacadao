from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from src.models.enums import DiscountTypeEnum, PaymentMethodEnum


class CheckoutPreviewRequestSchema(BaseModel):
    address_id: UUID
    coupon_code: Optional[str] = Field(None, max_length=50)


class CheckoutConfirmSchema(CheckoutPreviewRequestSchema):
    shipping_service_id: int
    expected_total_amount: Decimal = Field(ge=0)
    payment_method: PaymentMethodEnum
    installments: int = Field(1, ge=1)

    @model_validator(mode="after")
    def validate_installments(self) -> "CheckoutConfirmSchema":
        if self.payment_method != PaymentMethodEnum.CREDIT_CARD and self.installments != 1:
            raise ValueError("Pix e boleto aceitam somente uma parcela.")
        return self


class CheckoutItemPreviewSchema(BaseModel):
    variant_id: UUID
    product_name: str
    variation_name: str
    sku: str
    quantity: int
    base_unit_price: Decimal
    unit_price: Decimal
    pricing_tier_min_quantity: Optional[int] = None
    subtotal: Decimal


class CheckoutShippingOptionSchema(BaseModel):
    service_id: int
    service_name: Optional[str] = None
    company_name: Optional[str] = None
    price: Decimal
    delivery_time_days: Optional[int] = None
    discount_amount: Decimal
    total_amount: Decimal


class CheckoutPreviewResponseSchema(BaseModel):
    items: List[CheckoutItemPreviewSchema]
    subtotal_amount: Decimal
    coupon_code: Optional[str] = None
    discount_type: Optional[DiscountTypeEnum] = None
    shipping_options: List[CheckoutShippingOptionSchema]
