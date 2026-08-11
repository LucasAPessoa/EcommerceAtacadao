from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.schemas.base_schema import TimestampMixinSchema
from src.schemas.catalog.product_variant_schema import ProductVariantResponseSchema


class CartItemCreateSchema(BaseModel):
    variant_id: UUID
    quantity: int = Field(1, gt=0)


class CartItemUpdateSchema(BaseModel):
    quantity: int = Field(..., gt=0)


class CartItemResponseSchema(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    variant: ProductVariantResponseSchema

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.variant.base_price * self.quantity, 2)


class CartResponseSchema(TimestampMixinSchema):
    id: UUID
    user_id: UUID
    items: List[CartItemResponseSchema] = []

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

    @computed_field
    @property
    def total_amount(self) -> float:
        return round(sum(item.subtotal for item in self.items), 2)
