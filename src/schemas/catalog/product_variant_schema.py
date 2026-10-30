from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from src.schemas.base_schema import SoftDeleteMixinSchema


class ProductVariantBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    bling_sku: str = Field(..., max_length=100)
    variation_name: str = Field(..., max_length=100)
    gtin: Optional[str] = Field(None, max_length=50)
    packaging_gtin: Optional[str] = Field(None, max_length=50)
    base_price: Decimal = Field(..., ge=0)
    stock_quantity: int = Field(0, ge=0)
    last_bling_sync: Optional[datetime] = None
    is_active: bool = True
    weight_kg: Optional[float] = Field(None, ge=0)
    height_cm: Optional[float] = Field(None, ge=0)
    width_cm: Optional[float] = Field(None, ge=0)
    length_cm: Optional[float] = Field(None, ge=0)


class ProductVariantResponseSchema(ProductVariantBaseSchema, SoftDeleteMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)


class VariantTierSchema(BaseModel):
    id: UUID
    min_quantity: int
    unit_price: Decimal
    model_config = ConfigDict(from_attributes=True)


class ProductVariantPublicSchema(ProductVariantResponseSchema):
    """Variação na loja pública: preço de 1 unidade e tabela completa (spec 008)."""

    pricing_tiers: List[VariantTierSchema] = []

    @computed_field  # type: ignore[prop-decorator]  # padrão de computed_field do pydantic
    @property
    def unit_price(self) -> Optional[Decimal]:
        line_one = next((t for t in self.pricing_tiers if t.min_quantity == 1), None)
        return line_one.unit_price if line_one else None

    @field_validator("pricing_tiers", mode="after")
    @classmethod
    def _sorted(cls, tiers: List[VariantTierSchema]) -> List[VariantTierSchema]:
        return sorted(tiers, key=lambda t: t.min_quantity)
