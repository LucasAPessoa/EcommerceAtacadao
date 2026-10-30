"""Schemas do portal admin para produtos (contracts/http-api.md, seção Produtos)."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, PlainSerializer

_CENT = Decimal("0.01")


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


Money = Annotated[Decimal, PlainSerializer(_money, return_type=str, when_used="json")]


class PendingReason(str, Enum):
    INCOMPLETE_WEIGHT = "INCOMPLETE_WEIGHT"
    INCOMPLETE_DIMENSIONS = "INCOMPLETE_DIMENSIONS"
    INCOMPLETE_PRICE = "INCOMPLETE_PRICE"
    # Pendências de preço da loja (spec 008); na API saem em minúsculas, como "warnings".
    PRICE_NOT_SET = "PRICE_NOT_SET"
    STORE_PRICE_MISSING = "STORE_PRICE_MISSING"
    TIER_NOT_BELOW_UNIT = "TIER_NOT_BELOW_UNIT"


class PricingWarning(str, Enum):
    TIER_NOT_BELOW_UNIT = "tier_not_below_unit"
    STORE_PRICE_MISSING = "store_price_missing"
    PRICE_NOT_SET = "price_not_set"


class PricingStatusValue(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class PriceSourceValue(str, Enum):
    VARIANT_LINK = "variant_link"
    PARENT_LINK = "parent_link"
    GENERAL = "general"


class AdminProductListItem(BaseModel):
    id: UUID
    code: Optional[str] = None
    name: str
    bling_name: str
    main_image_url: Optional[str] = None
    is_active: bool
    visible: bool
    featured: bool
    store_listed: bool
    pricing_status: PricingStatusValue
    warnings: list[PricingWarning] = []
    min_price: Optional[Money] = None
    max_price: Optional[Money] = None
    stock: int
    low_stock: bool
    pending_count: int
    updated_at: datetime


class AdminVariant(BaseModel):
    id: UUID
    bling_sku: str
    gtin: Optional[str] = None
    variation_name: str
    base_price: Money
    stock_quantity: int
    is_active: bool
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None
    pending_reason: Optional[PendingReason] = None
    images: list[str] = []
    published: bool = False
    price_source: Optional[PriceSourceValue] = None
    store_price: Optional[Money] = None
    pricing_status: PricingStatusValue = PricingStatusValue.PENDING
    pricing_confirmed_at: Optional[datetime] = None
    # Sempre começa pela linha de min_quantity = 1.
    pricing_tiers: list["AdminPricingTier"] = []
    warnings: list[PricingWarning] = []


class AdminPricingTier(BaseModel):
    id: UUID
    min_quantity: int
    unit_price: Money


class BlingCategory(BaseModel):
    id: UUID
    name: str


class UpdatedBy(BaseModel):
    id: UUID
    full_name: str


class AdminPresentation(BaseModel):
    """Só o que o admin controla no site: ``visible`` e ``featured`` (o resto vem do Bling)."""

    visible: bool
    featured: bool
    updated_at: Optional[datetime] = None
    updated_by: Optional[UpdatedBy] = None


class AdminProductDetail(BaseModel):
    id: UUID
    bling_id: Optional[int] = None
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    complementary_description: Optional[str] = None
    images: list[str] = []
    categories: list[BlingCategory] = []
    brand: Optional[str] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    is_active: bool
    bling_updated_at: Optional[datetime] = None
    variants: list[AdminVariant]
    presentation: AdminPresentation
