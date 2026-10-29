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


class PricingTierResponseSchema(PricingTierBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: Optional[UUID] = None  # legado: as linhas por variação não têm produto
    variant_id: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)
