from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from src.schemas.base_schema import TimestampMixinSchema

class ProductListingBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    status: int

class ProductListingCreateSchema(ProductListingBaseSchema):
    product_id: UUID

class ProductListingUpdateSchema(BaseModel):
    bling_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[int] = None

class ProductListingResponseSchema(ProductListingBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)