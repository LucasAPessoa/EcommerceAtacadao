"""Schemas das rotas admin de preço (contracts/http-api.md, seção Admin)."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.admin.products import AdminPricingTier, Money


class PriceTierPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_quantity: int = Field(ge=1, le=1_000_000)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class VariantPricingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tiers: list[PriceTierPayload] = Field(default_factory=list, max_length=50)


class AdminVariantPricing(BaseModel):
    """Variação no formato do detalhe do contrato (campos de preço)."""

    id: UUID
    variation_name: str
    is_active: bool
    published: bool
    price_source: Optional[str] = None
    store_price: Optional[Money] = None
    pricing_status: str
    pricing_confirmed_at: Optional[datetime] = None
    pricing_tiers: list[AdminPricingTier]


class ConfirmPricingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[UUID] = Field(min_length=1, max_length=500)


class ConfirmPricingResult(BaseModel):
    confirmed: int
    skipped: list[UUID]


class PricingSettings(BaseModel):
    auto_confirm: bool
    store_configured: bool
    store_id: Optional[int] = None


class PricingSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_confirm: bool
