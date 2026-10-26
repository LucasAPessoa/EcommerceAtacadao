from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.base_schema import TimestampMixinSchema


class ProductListingBaseSchema(BaseModel):
    bling_id: Optional[int] = None
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    status: int


class ProductListingResponseSchema(ProductListingBaseSchema, TimestampMixinSchema):
    id: UUID
    product_id: UUID
    model_config = ConfigDict(from_attributes=True)
