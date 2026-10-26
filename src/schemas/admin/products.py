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


class AdminProductListItem(BaseModel):
    id: UUID
    code: Optional[str] = None
    name: str
    bling_name: str
    main_image_url: Optional[str] = None
    is_active: bool
    visible: bool
    featured: bool
    customized: bool
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


class AdminPricingTier(BaseModel):
    id: UUID
    min_quantity: int
    unit_price: Money


class TextField(BaseModel):
    bling: Optional[str] = None
    site: Optional[str] = None
    locked: bool


class BlingCategory(BaseModel):
    id: UUID
    name: str


class SiteCategory(BaseModel):
    id: UUID
    name: str
    is_active: bool


class CategoriesField(BaseModel):
    bling: list[BlingCategory]
    site: list[SiteCategory]
    locked: bool


class UpdatedBy(BaseModel):
    id: UUID
    full_name: str


class AdminPresentation(BaseModel):
    name: TextField
    description: TextField
    complementary_description: TextField
    categories: CategoriesField
    visible: bool
    featured: bool
    updated_at: Optional[datetime] = None
    updated_by: Optional[UpdatedBy] = None


class AdminProductDetail(BaseModel):
    id: UUID
    bling_id: Optional[int] = None
    code: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    is_active: bool
    bling_updated_at: Optional[datetime] = None
    variants: list[AdminVariant]
    pricing_tiers: list[AdminPricingTier]
    presentation: AdminPresentation
