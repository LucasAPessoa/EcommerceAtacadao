from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from src.schemas.base_schema import SoftDeleteMixinSchema

class ProductVariantBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    bling_sku: str = Field(..., max_length=100)
    variation_name: str = Field(..., max_length=100)
    gtin: Optional[str] = Field(None, max_length=50)
    packaging_gtin: Optional[str] = Field(None, max_length=50)
    base_price: float
    stock_quantity: int = 0
    last_bling_sync: Optional[datetime] = None
    is_active: bool = True
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None

class ProductVariantCreateSchema(ProductVariantBaseSchema):
    product_id: UUID

class ProductVariantUpdateSchema(BaseModel):
    bling_id: Optional[int] = None
    bling_sku: Optional[str] = Field(None, max_length=100)
    variation_name: Optional[str] = Field(None, max_length=100)
    gtin: Optional[str] = Field(None, max_length=50)
    packaging_gtin: Optional[str] = Field(None, max_length=50)
    base_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    last_bling_sync: Optional[datetime] = None
    is_active: Optional[bool] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None

class ProductVariantResponseSchema(ProductVariantBaseSchema, SoftDeleteMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)