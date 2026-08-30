from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class PricingTierBaseSchema(BaseModel):
    min_quantity: int = Field(
        ..., gt=0, description="Quantidade mínima da faixa, deve ser positiva"
    )
    unit_price: Decimal = Field(..., ge=0, description="Preço unitário, não pode ser negativo")


class PricingTierCreateSchema(PricingTierBaseSchema):
    product_id: UUID


class PricingTierUpdateSchema(BaseModel):
    min_quantity: Optional[int] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)


class PricingTierResponseSchema(PricingTierBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)
